"""Profile lookup, financial identity, analysis and transactions."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from .. import schemas as S
from ..database import get_db
from ..services import pan as P
from ..services.cleaning import ALL_CATEGORIES, standardise_category
from ..auth import Current, ProfileCtx, audit, can_read, current_account, profile_reader, profile_writer
from ..config import SANDBOX_TTL_HOURS
from ..services import sandbox
from . import common

router = APIRouter(prefix="/api", tags=["Profiles & analysis"])


DEMO_NOTICE = ("You are exploring a synthetic demo identity. It does not belong to a real person and no bank data was fetched: "
               "Finora never uses a PAN to look up real financial information. This is your own private copy - edit it freely, "
               "use Reset to restore the original, and it is deleted automatically {hours} hours after you opened it.")

DEMO_DESCRIPTIONS = {"balanced": "Salaried, balanced saver", "spender": "High spender, three credit cards",
                     "loan_heavy": "Home, car and personal loans", "irregular": "Freelancer, irregular income"}


def _explore(db: Session, template: M.User, cur: Current, request: Request) -> dict:
    sandbox.purge_expired(db)
    sb, created = sandbox.open_for(db, template, cur.user.id)
    audit(db, "demo.explore", request=request, app_user_id=cur.user.id, profile_id=sb.id,
          detail={"template": template.internal_id, "created": created})
    return {"found": True, "created": created, "profile": common.public_profile(sb),
            "notice": DEMO_NOTICE.format(hours=SANDBOX_TTL_HOURS)}


@router.get("/demo/templates", summary="The four synthetic demo identities you can explore")
def demo_templates(cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.User).where(M.User.kind == "template").order_by(M.User.id)).all()
    return [{"template_id": t.internal_id, "name": t.name, "pan_masked": t.pan_masked, "age": t.age, "occupation": t.occupation,
             "city": t.city, "description": DEMO_DESCRIPTIONS.get(t.archetype, ""), "synthetic": True} for t in rows]


@router.post("/demo/explore", summary="Open your own editable, expiring copy (sandbox) of a demo identity")
def explore_demo(body: S.ExploreIn, request: Request, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    t = db.scalar(select(M.User).where(M.User.internal_id == body.template_id, M.User.kind == "template"))
    if t is None:
        raise HTTPException(404, "Unknown demo identity.")
    return _explore(db, t, cur, request)


@router.post("/lookup", summary="Open a demo identity by its demo identifier (sent in the body, never in the URL)")
def lookup(body: S.LookupIn, request: Request, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    err = P.validation_error(body.pan)
    if err:
        raise HTTPException(422, err)
    # Only the four synthetic demo identifiers resolve. Any other PAN - including a real one - finds nothing,
    # because Finora has no connection to banks, credit bureaus or the income-tax department.
    t = db.scalar(select(M.User).where(M.User.pan_hash == P.hash_pan(body.pan), M.User.kind == "template"))
    if t is None:
        raise HTTPException(404, "That is not one of the demo identifiers. Finora cannot fetch real financial data from a PAN - "
                                 "explore a demo identity or build your own profile instead.")
    return _explore(db, t, cur, request)


@router.post("/profiles/{internal_id}/reset", summary="Reset a demo sandbox to the original demo identity")
def reset_sandbox(request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    if ctx.profile.kind != "sandbox":
        raise HTTPException(422, "Only demo sandboxes can be reset.")
    old_id = ctx.profile.id
    sb = sandbox.reset(db, ctx.profile)
    common.invalidate(old_id)
    audit(db, "demo.reset", request=request, app_user_id=ctx.account.id, profile_id=sb.id)
    return {"reset": True, "profile": common.public_profile(sb)}


@router.get("/profiles", summary="Profiles you can open: the demo templates plus your own (PAN shown masked only)")
def list_profiles(cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    users = db.scalars(select(M.User).where((M.User.kind == "template") | (M.User.owner_id == cur.user.id))
                       .order_by(M.User.id)).all()
    return [common.public_profile(u) for u in users if can_read(u, cur.user)]


@router.get("/profiles/{internal_id}", summary="Basic profile")
def get_profile(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    return common.public_profile(ctx.profile)


@router.post("/profiles/{internal_id}/analyze", summary="Run the full analysis (all models + calculations) and save it")
def analyze(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    return _strip(common.get_analysis(db, user, refresh=True))


@router.get("/profiles/{internal_id}/analysis", summary="Latest analysis (computed on first request)")
def get_analysis(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    return _strip(common.get_analysis(db, ctx.profile))


def _strip(a: dict) -> dict:
    """Drop the bulky per-transaction score map from the main payload."""
    ml = {k: ({kk: vv for kk, vv in v.items() if kk != "scores"} if isinstance(v, dict) else v) for k, v in a["ml"].items()}
    return {**a, "ml": ml}


@router.get("/profiles/{internal_id}/accounts", summary="Bank accounts and credit cards")
def accounts(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    a = common.get_analysis(db, user)
    accts = db.scalars(select(M.BankAccount).where(M.BankAccount.user_id == user.id)).all()
    counts = dict(db.execute(select(M.Transaction.account_id, func.count()).where(M.Transaction.user_id == user.id)
                             .group_by(M.Transaction.account_id)).all())
    return {"accounts": [{"id": x.id, "bank_name": x.bank_name, "account_type": x.account_type, "account_masked": x.account_masked,
                          "balance": x.balance, "interest_rate": x.interest_rate, "is_primary": x.is_primary,
                          "transactions": counts.get(x.id, 0)} for x in accts],
            "cards": a["credit"].get("cards", []), "credit_summary": {k: v for k, v in a["credit"].items() if k != "cards"},
            "card_ids": [{"id": c.id, "label": f"{c.issuer} {c.card_name} ••{c.last4}"} for c in
                         db.scalars(select(M.CreditCard).where(M.CreditCard.user_id == user.id)).all()],
            "spend_by_source": a["cash_flow"]["spend_by_source"], "credit_risk": a["ml"].get("credit_risk")}


@router.get("/profiles/{internal_id}/transactions", summary="Transactions with filters and anomaly flags")
def transactions(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db), category: str | None = None,
                 source: str | None = Query(None, description="account:<id> or card:<id>"), flagged_only: bool = False,
                 month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), search: str | None = None,
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    user = ctx.profile
    a = common.get_analysis(db, user)
    an = a["ml"].get("anomaly", {})
    flagged = {f["transaction_id"]: f for f in an.get("flagged", [])}
    scores = an.get("scores", {})
    q = select(M.Transaction).where(M.Transaction.user_id == user.id)
    if category:
        q = q.where(M.Transaction.category == category)
    if source:
        kind, _, sid = source.partition(":")
        if kind == "account" and sid.isdigit():
            q = q.where(M.Transaction.account_id == int(sid))
        elif kind == "card" and sid.isdigit():
            q = q.where(M.Transaction.card_id == int(sid))
    if month:
        y, m = int(month[:4]), int(month[5:])
        q = q.where(M.Transaction.date >= date(y, m, 1), M.Transaction.date < (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(M.Transaction.raw_description.ilike(like) | M.Transaction.merchant.ilike(like))
    if flagged_only:
        q = q.where(M.Transaction.ref.in_(list(flagged)) if flagged else M.Transaction.id == -1)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(M.Transaction.date.desc(), M.Transaction.id.desc()).limit(limit).offset(offset)).all()
    accts = {x.id: f"{x.bank_name} {x.account_masked}" for x in db.scalars(select(M.BankAccount).where(M.BankAccount.user_id == user.id))}
    cards = {x.id: f"{x.issuer} {x.card_name} ••{x.last4}" for x in db.scalars(select(M.CreditCard).where(M.CreditCard.user_id == user.id))}
    items = []
    for t in rows:
        f = flagged.get(t.ref)
        items.append({"id": t.id, "ref": t.ref, "date": t.date.isoformat(), "amount": t.amount, "type": t.type,
                      "description": t.raw_description, "merchant": t.merchant, "category": t.category,
                      "category_source": t.category_source,
                      "source": cards.get(t.card_id) or accts.get(t.account_id) or "-", "source_kind": "card" if t.card_id else "account",
                      "anomaly_score": scores.get(t.ref), "flagged": f is not None,
                      "severity": f["severity"] if f else None, "reasons": f["reasons"] if f else None})
    months = [r[0] for r in db.execute(select(func.distinct(func.substr(func.cast(M.Transaction.date, M.String), 1, 7)))
                                       .where(M.Transaction.user_id == user.id)).all()]
    return {"total": total, "limit": limit, "offset": offset, "items": items, "categories": ALL_CATEGORIES,
            "months": sorted(months, reverse=True),
            "anomaly_summary": {k: an.get(k) for k in ["transactions_scored", "flagged_count", "flagged_amount_total", "by_category",
                                                        "by_month", "severity_rule", "disclaimer"]},
            "flagged": an.get("flagged", [])}


@router.patch("/profiles/{internal_id}/transactions/{tx_id}", summary="Correct a transaction's category")
def recategorise(tx_id: int, body: S.CategoryPatch, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    t = db.get(M.Transaction, tx_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found.")
    cat = standardise_category(body.category)
    if cat not in ALL_CATEGORIES:
        raise HTTPException(422, f"Unknown category. Choose one of: {', '.join(ALL_CATEGORIES)}")
    t.category, t.category_source = cat, "user"
    db.commit()
    common.invalidate(user.id)
    return {"id": t.id, "category": t.category, "category_source": t.category_source}


@router.get("/profiles/{internal_id}/recommendations", summary="Saved recommendations with their status")
def recommendations(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    common.get_analysis(db, user)
    rows = db.scalars(select(M.Recommendation).where(M.Recommendation.user_id == user.id)).all()
    order = {"high": 0, "medium": 1, "low": 2}
    out = [{"id": r.id, "code": r.code, "finding": r.finding, "evidence": r.evidence, "explanation": r.explanation,
            "action": r.action, "priority": r.priority, "impact_inr": r.impact_inr, "impact_text": r.impact_text,
            "source": r.source, "status": r.status} for r in rows]
    return sorted(out, key=lambda r: (r["status"] != "open", order[r["priority"]], -(r["impact_inr"] or 0)))


@router.patch("/profiles/{internal_id}/recommendations/{rec_id}", summary="Accept or dismiss a recommendation")
def set_recommendation_status(rec_id: int, body: S.RecStatus, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    r = db.get(M.Recommendation, rec_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Recommendation not found.")
    r.status = body.status
    db.commit()
    return {"id": r.id, "status": r.status}

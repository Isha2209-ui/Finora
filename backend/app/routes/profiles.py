"""Profile lookup, financial identity, analysis and transactions."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from .. import schemas as S
from ..database import get_db
from ..services import pan as P
from ..services.cleaning import ALL_CATEGORIES, standardise_category
from . import common

router = APIRouter(prefix="/api", tags=["Profiles & analysis"])


@router.post("/lookup", summary="Find a profile by PAN (sent in the body, never in the URL)")
def lookup(body: S.LookupIn, db: Session = Depends(get_db)):
    err = P.validation_error(body.pan)
    if err:
        raise HTTPException(422, err)
    user = db.scalar(select(M.User).where(M.User.pan_hash == P.hash_pan(body.pan)))
    if user is None:
        raise HTTPException(404, "No financial profile is linked to this PAN. Try one of the demo identifiers.")
    return {"found": True, "profile": common.public_profile(user),
            "notice": "Demo identifier mapped to a synthetic profile. A real PAN does not give access to anyone's financial data; "
                      "production access would use the RBI Account Aggregator framework with user consent."}


@router.get("/profiles", summary="List profiles (PAN shown masked only)")
def list_profiles(db: Session = Depends(get_db)):
    users = db.scalars(select(M.User).where(M.User.pan_hash.is_not(None)).order_by(M.User.id)).all()
    return [common.public_profile(u) for u in users]


@router.get("/profiles/{internal_id}", summary="Basic profile")
def get_profile(internal_id: str, db: Session = Depends(get_db)):
    return common.public_profile(common.get_user(db, internal_id))


@router.post("/profiles/{internal_id}/analyze", summary="Run the full analysis (all models + calculations) and save it")
def analyze(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    return _strip(common.get_analysis(db, user, refresh=True))


@router.get("/profiles/{internal_id}/analysis", summary="Latest analysis (computed on first request)")
def get_analysis(internal_id: str, db: Session = Depends(get_db)):
    return _strip(common.get_analysis(db, common.get_user(db, internal_id)))


def _strip(a: dict) -> dict:
    """Drop the bulky per-transaction score map from the main payload."""
    ml = {k: ({kk: vv for kk, vv in v.items() if kk != "scores"} if isinstance(v, dict) else v) for k, v in a["ml"].items()}
    return {**a, "ml": ml}


@router.get("/profiles/{internal_id}/accounts", summary="Bank accounts and credit cards")
def accounts(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
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
def transactions(internal_id: str, db: Session = Depends(get_db), category: str | None = None,
                 source: str | None = Query(None, description="account:<id> or card:<id>"), flagged_only: bool = False,
                 month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), search: str | None = None,
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    user = common.get_user(db, internal_id)
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
def recategorise(internal_id: str, tx_id: int, body: S.CategoryPatch, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
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
def recommendations(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    common.get_analysis(db, user)
    rows = db.scalars(select(M.Recommendation).where(M.Recommendation.user_id == user.id)).all()
    order = {"high": 0, "medium": 1, "low": 2}
    out = [{"id": r.id, "code": r.code, "finding": r.finding, "evidence": r.evidence, "explanation": r.explanation,
            "action": r.action, "priority": r.priority, "impact_inr": r.impact_inr, "impact_text": r.impact_text,
            "source": r.source, "status": r.status} for r in rows]
    return sorted(out, key=lambda r: (r["status"] != "open", order[r["priority"]], -(r["impact_inr"] or 0)))


@router.patch("/profiles/{internal_id}/recommendations/{rec_id}", summary="Accept or dismiss a recommendation")
def set_recommendation_status(internal_id: str, rec_id: int, body: S.RecStatus, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    r = db.get(M.Recommendation, rec_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Recommendation not found.")
    r.status = body.status
    db.commit()
    return {"id": r.id, "status": r.status}

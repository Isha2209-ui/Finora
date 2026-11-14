"""Reports, statement upload, profile & data management, model lab."""
from __future__ import annotations

from datetime import date, datetime

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from .. import schemas as S
from ..cfo import agent
from ..config import REPORTS_DIR
from ..database import get_db
from ..ml import categoriser, registry
from ..services import pan as P
from ..services import report as R
from ..services import statement_import
from ..services.cleaning import ALL_CATEGORIES, standardise_category
from ..auth import Current, ProfileCtx, audit, can_write, current_account, profile_reader, profile_writer, rate_limit
from ..config import ENABLE_RETRAIN_ENDPOINT, UPLOAD_MAX_BYTES, UPLOAD_MAX_PER_HOUR
from ..services.profile_ops import delete_profile_data
from . import common


def new_profile_id(db: Session) -> str:
    """Random, non-sequential ID for profiles created by account holders, so IDs cannot be guessed or enumerated."""
    while True:
        iid = f"FP_{secrets.token_hex(8).upper()}"
        if not db.scalar(select(M.User.id).where(M.User.internal_id == iid)):
            return iid

router = APIRouter(prefix="/api", tags=["Reports, data & models"])


# ---------------------------------------------------------------- reports
@router.get("/profiles/{internal_id}/report.pdf", summary="Download the Financial Intelligence Report (PDF)")
def report_pdf(request: Request, use_llm: bool = False, ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    a = common.get_analysis(db, user)
    brief = agent.briefing(common.cfo_context(db, user), use_llm=use_llm)["briefing"]
    pdf = R.build_pdf(a, brief, registry.metrics())
    name = f"Finora_Report_{user.internal_id}_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(3)}.pdf"
    (REPORTS_DIR / name).write_bytes(pdf)
    db.add(M.Report(user_id=user.id, app_user_id=ctx.account.id, report_path=str(REPORTS_DIR / name)))
    audit(db, "report.generate", request=request, app_user_id=ctx.account.id, profile_id=user.id, commit=False)
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/profiles/{internal_id}/export.zip", summary="Download all data and analysis as CSV files (zip)")
def export_zip(request: Request, ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    audit(db, "data.export", request=request, app_user_id=ctx.account.id, profile_id=user.id, detail={"format": "zip"})
    a = common.get_analysis(db, user)
    tx = [{"date": t.date.isoformat(), "amount": t.amount, "type": t.type, "category": t.category, "merchant": t.merchant,
           "description": t.raw_description, "ref": t.ref} for t in
          db.scalars(select(M.Transaction).where(M.Transaction.user_id == user.id).order_by(M.Transaction.date))]
    return Response(R.build_csv_zip(a, tx), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="Finora_Export_{user.internal_id}.zip"'})


@router.get("/profiles/{internal_id}/transactions.csv", summary="Download transactions as CSV")
def transactions_csv(request: Request, ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    audit(db, "data.export", request=request, app_user_id=ctx.account.id, profile_id=user.id, detail={"format": "transactions_csv"})
    lines = ["date,amount,type,category,merchant,description"]
    for t in db.scalars(select(M.Transaction).where(M.Transaction.user_id == user.id).order_by(M.Transaction.date)):
        desc = t.raw_description.replace('"', "'")
        lines.append(f'{t.date},{t.amount},{t.type},{t.category or ""},"{t.merchant or ""}","{desc}"')
    return Response("\n".join(lines), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="transactions_{user.internal_id}.csv"'})


@router.get("/profiles/{internal_id}/reports", summary="Reports you generated for this profile")
def reports(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    q = select(M.Report).where(M.Report.user_id == ctx.profile.id, M.Report.app_user_id == ctx.account.id)
    return [{"id": r.id, "file": Path(r.report_path).name, "created_at": r.created_at.isoformat()} for r in
            db.scalars(q.order_by(M.Report.id.desc()).limit(20))]


# ---------------------------------------------------------------- statement upload & categoriser
@router.post("/profiles/{internal_id}/upload", summary="Upload a bank/card statement CSV; it is cleaned and categorised by the ML model")
async def upload(request: Request, file: UploadFile = File(...), account_id: int | None = Form(None),
                 card_id: int | None = Form(None), ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    rate_limit(f"upload:{ctx.account.id}", UPLOAD_MAX_PER_HOUR, 3600, "Too many uploads in the last hour.")
    content = await file.read(UPLOAD_MAX_BYTES + 1)  # never read more than the limit into memory
    if len(content) > UPLOAD_MAX_BYTES:
        audit(db, "statement.upload", request=request, app_user_id=ctx.account.id, profile_id=user.id, outcome="denied",
              detail={"reason": "too_large"})
        raise HTTPException(413, f"File too large (limit {UPLOAD_MAX_BYTES // 1_000_000} MB).")
    if account_id and db.scalar(select(M.BankAccount.user_id).where(M.BankAccount.id == account_id)) != user.id:
        raise HTTPException(422, "That account does not belong to this profile.")
    if card_id and db.scalar(select(M.CreditCard.user_id).where(M.CreditCard.id == card_id)) != user.id:
        raise HTTPException(422, "That card does not belong to this profile.")
    if not account_id and not card_id:
        account_id = db.scalar(select(M.BankAccount.id).where(M.BankAccount.user_id == user.id).order_by(M.BankAccount.is_primary.desc()))
    try:
        res = statement_import.import_statement(db, user, content, account_id, card_id)
    except ValueError as e:
        audit(db, "statement.upload", request=request, app_user_id=ctx.account.id, profile_id=user.id, outcome="failed")
        raise HTTPException(422, str(e))
    common.invalidate(user.id)
    audit(db, "statement.upload", request=request, app_user_id=ctx.account.id, profile_id=user.id,
          detail={"added": res.get("transactions_added"), "skipped": res.get("duplicates_skipped")})
    return {"filename": Path(file.filename or "statement.csv").name[:120], **res}


@router.post("/categorise", summary="Try the transaction categoriser on any narration text")
def categorise(body: dict):
    texts = [str(t)[:200] for t in (body.get("texts") or [])][:50]
    if not texts:
        raise HTTPException(422, "Send {\"texts\": [\"UPI/DR/.../SWIGGY/...\"]}")
    preds = categoriser.predict(registry.get("categoriser"), texts)
    return [{"text": t, **p, "keyword_rule": categoriser.keyword_rule(t)} for t, p in zip(texts, preds)]


# ---------------------------------------------------------------- profile & data management
@router.post("/profiles", summary="Create your own private profile (then add data or upload a statement)")
def create_profile(body: S.ProfileIn, request: Request, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    masked = None
    if body.pan:  # optional, for display only: never hashed for lookup, never used to fetch anything
        err = P.validation_error(body.pan)
        if err:
            raise HTTPException(422, err)
        masked = P.mask(body.pan)
    iid = new_profile_id(db)
    u = M.User(internal_id=iid, pan_hash=None, pan_masked=masked, name=body.name, age=body.age,
               occupation=body.occupation, employment_type=body.employment_type, city=body.city,
               retirement_age_target=body.retirement_age_target, is_demo=False, archetype="custom",
               kind="private", owner_id=cur.user.id)
    db.add(u)
    db.flush()
    acct = M.BankAccount(user_id=u.id, bank_name=body.bank_name, account_type="savings", account_masked="XXXX0001",
                         balance=body.bank_balance, interest_rate=3.0, is_primary=True)
    db.add(acct)
    db.flush()
    # six months of the stated income so ratios are meaningful before a statement is uploaded
    for y, m in [(2026, k) for k in range(5, 11)]:
        db.add(M.IncomeRecord(user_id=u.id, account_id=acct.id, amount=body.monthly_income,
                              source="Salary" if body.employment_type == "salaried" else "Client payment", date=date(y, m, 1)))
    audit(db, "profile.create", request=request, app_user_id=cur.user.id, profile_id=u.id, commit=False)
    db.commit()
    return {"created": True, "profile": common.public_profile(u), "account_id": acct.id,
            "next_step": "Upload a statement CSV for this profile to analyse it."}


@router.patch("/profiles/{internal_id}", summary="Edit profile details")
def patch_profile(body: S.ProfilePatch, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    common.invalidate(user.id)
    return common.public_profile(user)


@router.delete("/profiles/{internal_id}", summary="Delete one of your profiles and all of its data (demo templates are protected)")
def delete_profile(request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    uid, iid, kind = user.id, user.internal_id, user.kind
    rows = delete_profile_data(db, user)
    audit(db, "profile.delete", request=request, app_user_id=ctx.account.id, profile_id=uid, commit=False,
          detail={"kind": kind, "rows_deleted": rows})
    db.commit()
    common.invalidate(uid)
    return {"deleted": iid, "rows_deleted": rows}


@router.post("/profiles/{internal_id}/transactions", summary="Add one transaction (category predicted if not given)")
def add_transaction(body: S.TransactionIn, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    cat, src = standardise_category(body.category), "user"
    if not cat:
        p = categoriser.predict(registry.get("categoriser"), [body.description])[0]
        cat, src = p["category"], "model"
    elif cat not in ALL_CATEGORIES:
        raise HTTPException(422, f"Unknown category. Choose one of: {', '.join(ALL_CATEGORIES)}")
    account_id = body.account_id
    if not account_id and not body.card_id:
        account_id = db.scalar(select(M.BankAccount.id).where(M.BankAccount.user_id == user.id).order_by(M.BankAccount.is_primary.desc()))
    n = db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.user_id == user.id)) or 0
    t = M.Transaction(user_id=user.id, account_id=account_id, card_id=body.card_id, ref=f"{user.internal_id[-6:]}-M{n + 1:05d}",
                      date=body.date, amount=body.amount, type=body.type, raw_description=body.description, category=cat,
                      category_source=src)
    db.add(t)
    db.commit()
    common.invalidate(user.id)
    return {"id": t.id, "ref": t.ref, "category": cat, "category_source": src}


@router.delete("/profiles/{internal_id}/transactions/{tx_id}", summary="Delete one transaction")
def delete_transaction(tx_id: int, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    t = db.get(M.Transaction, tx_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found.")
    db.delete(t)
    db.commit()
    common.invalidate(user.id)
    return {"deleted": tx_id}


@router.get("/profiles/{internal_id}/data-summary", summary="Row counts per table for this profile")
def data_summary(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    user = ctx.profile
    tables = {"Bank accounts": M.BankAccount, "Credit cards": M.CreditCard, "Transactions": M.Transaction, "Income records": M.IncomeRecord,
              "Recurring payments": M.RecurringPayment, "Stocks": M.StockHolding, "Mutual funds": M.MutualFundHolding, "SIPs": M.SIP,
              "Fixed deposits": M.FixedDeposit, "Properties": M.Property, "Other assets": M.OtherAsset, "Loans": M.Loan,
              "Insurance policies": M.InsurancePolicy, "Goals": M.Goal, "Recommendations": M.Recommendation, "Reports": M.Report}
    return {"profile": common.public_profile(user), "can_delete": can_write(user, ctx.account),
            "tables": [{"table": k, "rows": db.scalar(select(func.count()).select_from(v).where(v.user_id == user.id))} for k, v in tables.items()]}


# ---------------------------------------------------------------- model lab
@router.get("/models/metrics", summary="Training and evaluation metrics for every model")
def model_metrics():
    m = registry.metrics()
    if not m:
        raise HTTPException(503, "Models are not trained yet. Run: python -m app.ml.train")
    return {"status": registry.status(), **m}


@router.post("/models/retrain", summary="Retrain all models on the synthetic population + public datasets (local only, ~40 s)")
def retrain(request: Request, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    if not ENABLE_RETRAIN_ENDPOINT:
        raise HTTPException(403, "Retraining through the API is disabled on this server. Run: python -m app.ml.train")
    rate_limit("retrain", 2, 600, "Retraining was started recently.")
    from ..ml import train
    audit(db, "models.retrain", request=request, app_user_id=cur.user.id)
    m = train.run(verbose=False)
    registry.reload()
    common.invalidate()
    return {"retrained": True, "trained_at": m["trained_at"],
            "training_seconds": {k: v["training_seconds"] for k, v in m.items() if isinstance(v, dict) and "training_seconds" in v}}

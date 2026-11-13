"""Reports, statement upload, profile & data management, model lab."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select
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
from . import common

router = APIRouter(prefix="/api", tags=["Reports, data & models"])


# ---------------------------------------------------------------- reports
@router.get("/profiles/{internal_id}/report.pdf", summary="Download the Financial Intelligence Report (PDF)")
def report_pdf(internal_id: str, use_llm: bool = False, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    a = common.get_analysis(db, user)
    brief = agent.briefing(common.cfo_context(db, user), use_llm=use_llm)["briefing"]
    pdf = R.build_pdf(a, brief, registry.metrics())
    name = f"Finora_Report_{user.internal_id}_{datetime.now():%Y%m%d_%H%M}.pdf"
    (REPORTS_DIR / name).write_bytes(pdf)
    db.add(M.Report(user_id=user.id, report_path=str(REPORTS_DIR / name)))
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/profiles/{internal_id}/export.zip", summary="Download all data and analysis as CSV files (zip)")
def export_zip(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    a = common.get_analysis(db, user)
    tx = [{"date": t.date.isoformat(), "amount": t.amount, "type": t.type, "category": t.category, "merchant": t.merchant,
           "description": t.raw_description, "ref": t.ref} for t in
          db.scalars(select(M.Transaction).where(M.Transaction.user_id == user.id).order_by(M.Transaction.date))]
    return Response(R.build_csv_zip(a, tx), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="Finora_Export_{user.internal_id}.zip"'})


@router.get("/profiles/{internal_id}/transactions.csv", summary="Download transactions as CSV")
def transactions_csv(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    lines = ["date,amount,type,category,merchant,description"]
    for t in db.scalars(select(M.Transaction).where(M.Transaction.user_id == user.id).order_by(M.Transaction.date)):
        desc = t.raw_description.replace('"', "'")
        lines.append(f'{t.date},{t.amount},{t.type},{t.category or ""},"{t.merchant or ""}","{desc}"')
    return Response("\n".join(lines), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="transactions_{user.internal_id}.csv"'})


@router.get("/profiles/{internal_id}/reports", summary="Previously generated reports")
def reports(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    return [{"id": r.id, "file": r.report_path.split("/")[-1], "created_at": r.created_at.isoformat()} for r in
            db.scalars(select(M.Report).where(M.Report.user_id == user.id).order_by(M.Report.id.desc()).limit(20))]


# ---------------------------------------------------------------- statement upload & categoriser
@router.post("/profiles/{internal_id}/upload", summary="Upload a bank/card statement CSV; it is cleaned and categorised by the ML model")
async def upload(internal_id: str, file: UploadFile = File(...), account_id: int | None = Form(None),
                 card_id: int | None = Form(None), db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    content = await file.read()
    if len(content) > 5_000_000:
        raise HTTPException(413, "File too large (limit 5 MB).")
    if account_id and db.scalar(select(M.BankAccount.user_id).where(M.BankAccount.id == account_id)) != user.id:
        raise HTTPException(422, "That account does not belong to this profile.")
    if card_id and db.scalar(select(M.CreditCard.user_id).where(M.CreditCard.id == card_id)) != user.id:
        raise HTTPException(422, "That card does not belong to this profile.")
    if not account_id and not card_id:
        account_id = db.scalar(select(M.BankAccount.id).where(M.BankAccount.user_id == user.id).order_by(M.BankAccount.is_primary.desc()))
    try:
        res = statement_import.import_statement(db, user, content, account_id, card_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    common.invalidate(user.id)
    return {"filename": file.filename, **res}


@router.post("/categorise", summary="Try the transaction categoriser on any narration text")
def categorise(body: dict):
    texts = [str(t)[:200] for t in (body.get("texts") or [])][:50]
    if not texts:
        raise HTTPException(422, "Send {\"texts\": [\"UPI/DR/.../SWIGGY/...\"]}")
    preds = categoriser.predict(registry.get("categoriser"), texts)
    return [{"text": t, **p, "keyword_rule": categoriser.keyword_rule(t)} for t, p in zip(texts, preds)]


# ---------------------------------------------------------------- profile & data management
@router.post("/profiles", summary="Create a new profile (then upload a statement to fill it)")
def create_profile(body: S.ProfileIn, db: Session = Depends(get_db)):
    err = P.validation_error(body.pan)
    if err:
        raise HTTPException(422, err)
    h = P.hash_pan(body.pan)
    if db.scalar(select(M.User.id).where(M.User.pan_hash == h)):
        raise HTTPException(409, "A profile with this PAN already exists.")
    n = (db.scalar(select(func.count()).select_from(M.User).where(M.User.internal_id.like("FINORA_USER_%"))) or 0) + 1
    while db.scalar(select(M.User.id).where(M.User.internal_id == f"FINORA_USER_{n:03d}")):
        n += 1
    u = M.User(internal_id=f"FINORA_USER_{n:03d}", pan_hash=h, pan_masked=P.mask(body.pan), name=body.name, age=body.age,
               occupation=body.occupation, employment_type=body.employment_type, city=body.city,
               retirement_age_target=body.retirement_age_target, is_demo=True, archetype="custom")
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
    db.commit()
    return {"created": True, "profile": common.public_profile(u), "account_id": acct.id,
            "next_step": "Upload a statement CSV for this profile to analyse it."}


@router.patch("/profiles/{internal_id}", summary="Edit profile details")
def patch_profile(internal_id: str, body: S.ProfilePatch, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    common.invalidate(user.id)
    return common.public_profile(user)


@router.delete("/profiles/{internal_id}", summary="Delete a custom profile (the four built-in demo profiles are protected)")
def delete_profile(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    if user.archetype != "custom":
        raise HTTPException(403, "Built-in demo profiles cannot be deleted.")
    uid = user.id
    card_ids = [c for (c,) in db.execute(select(M.CreditCard.id).where(M.CreditCard.user_id == uid))]
    if card_ids:
        db.execute(delete(M.CardStatement).where(M.CardStatement.card_id.in_(card_ids)))
    for model in [M.Transaction, M.IncomeRecord, M.RecurringPayment, M.StockHolding, M.MutualFundHolding, M.SIP, M.FixedDeposit,
                  M.OtherAsset, M.Loan, M.InsurancePolicy, M.Goal, M.SavingsRecord, M.MonthlySummary, M.NetWorthSnapshot,
                  M.AnalysisResult, M.Recommendation, M.Report, M.ChatMessage, M.Property, M.CreditCard, M.BankAccount]:
        db.execute(delete(model).where(model.user_id == uid))
    db.delete(user)
    db.commit()
    common.invalidate(uid)
    return {"deleted": internal_id}


@router.post("/profiles/{internal_id}/transactions", summary="Add one transaction (category predicted if not given)")
def add_transaction(internal_id: str, body: S.TransactionIn, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
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
def delete_transaction(internal_id: str, tx_id: int, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    t = db.get(M.Transaction, tx_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found.")
    db.delete(t)
    db.commit()
    common.invalidate(user.id)
    return {"deleted": tx_id}


@router.get("/profiles/{internal_id}/data-summary", summary="Row counts per table for this profile")
def data_summary(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    tables = {"Bank accounts": M.BankAccount, "Credit cards": M.CreditCard, "Transactions": M.Transaction, "Income records": M.IncomeRecord,
              "Recurring payments": M.RecurringPayment, "Stocks": M.StockHolding, "Mutual funds": M.MutualFundHolding, "SIPs": M.SIP,
              "Fixed deposits": M.FixedDeposit, "Properties": M.Property, "Other assets": M.OtherAsset, "Loans": M.Loan,
              "Insurance policies": M.InsurancePolicy, "Goals": M.Goal, "Recommendations": M.Recommendation, "Reports": M.Report}
    return {"profile": common.public_profile(user), "can_delete": user.archetype == "custom",
            "tables": [{"table": k, "rows": db.scalar(select(func.count()).select_from(v).where(v.user_id == user.id))} for k, v in tables.items()]}


# ---------------------------------------------------------------- model lab
@router.get("/models/metrics", summary="Training and evaluation metrics for every model")
def model_metrics():
    m = registry.metrics()
    if not m:
        raise HTTPException(503, "Models are not trained yet. Run: python -m app.ml.train")
    return {"status": registry.status(), **m}


@router.post("/models/retrain", summary="Retrain all models on the current database (takes ~40 seconds)")
def retrain():
    from ..ml import train
    m = train.run(verbose=False)
    registry.reload()
    common.invalidate()
    return {"retrained": True, "trained_at": m["trained_at"],
            "training_seconds": {k: v["training_seconds"] for k, v in m.items() if isinstance(v, dict) and "training_seconds" in v}}

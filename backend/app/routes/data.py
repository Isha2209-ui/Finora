"""Reports, statement upload, profile & data management, model lab."""
from __future__ import annotations

from datetime import datetime

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
import pandas as pd
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
        res = statement_import.import_statement(db, user, content, account_id, card_id, app_user_id=ctx.account.id,
                                                filename=Path(file.filename or "statement.csv").name)
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
    preds = categoriser.safe_predict(texts)
    out = []
    for t, p in zip(texts, preds):
        why = None
        if p["source"] == "model":
            why = categoriser.explain(registry.get("categoriser"), t)
        elif p["source"] == "rule":
            why = ["bank-side rule (Rent, EMI, Investment, Transfer, Card Payment or Cash narration)"]
        out.append({"text": t, **p, "why": why, "keyword_rule": categoriser.keyword_rule(t)})
    return out


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
    audit(db, "profile.create", request=request, app_user_id=cur.user.id, profile_id=u.id, commit=False)
    db.commit()
    return {"created": True, "profile": common.public_profile(u),
            "next_step": "Add your accounts, income, holdings and loans, or upload a bank statement CSV."}


@router.patch("/profiles/{internal_id}", summary="Edit profile details")
def patch_profile(body: S.ProfilePatch, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    user = ctx.profile
    changes = body.model_dump(exclude_none=True)
    age = changes.get("age", user.age)
    if changes.get("retirement_age_target", user.retirement_age_target) <= age:
        raise HTTPException(422, "Target retirement age must be above your current age.")
    for k, v in changes.items():
        setattr(user, k, v)
    audit(db, "profile.update", request=request, app_user_id=ctx.account.id, profile_id=user.id, detail={"fields": sorted(changes)}, commit=False)
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
        p = categoriser.safe_predict([body.description])[0]
        cat, src = p["category"], (p["source"] if p["source"] != "none" else "model")
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
@router.get("/models/metrics", summary="Training and evaluation metrics of the active models")
def model_metrics():
    m = registry.metrics()
    if not m:
        raise HTTPException(503, "No approved real-data model is active yet. Run: python -m app.ml.train")
    return {"status": registry.status(), **m}


class CreditMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: int = Field(ge=-2, le=8, description="-2 no use, -1 paid in full, 0 revolving, 1..8 months late")
    bill: float = Field(ge=-1_000_000, le=100_000_000)
    paid: float = Field(ge=0, le=100_000_000)


class CreditScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: int = Field(ge=18, le=100)
    credit_limit: float = Field(gt=0, le=100_000_000)
    months: list[CreditMonth] = Field(min_length=3, max_length=6, description="most recent month first")


@router.post("/models/credit-risk/score", summary="Score a card history you enter with the real credit-risk model (XGBoost + SHAP)")
def credit_risk_score(body: CreditScoreIn, cur: Current = Depends(current_account)):
    """Runs the ACTIVE credit-risk model on the inputs: the 14 engineered features, the default probability and every
    feature's SHAP contribution. Nothing is stored."""
    import shap
    from ..ml import credit_risk as CR
    try:
        art = registry.get("credit_risk")
    except registry.ModelUnavailable as e:
        raise HTTPException(503, str(e))
    feats = CR.features_from_history(body.age, body.credit_limit, [m.status for m in body.months],
                                     [m.bill for m in body.months], [m.paid for m in body.months])
    X = pd.DataFrame([feats])[CR.FEATURES]
    p = float(art["model"].predict_proba(X)[:, 1][0])
    sv = shap.TreeExplainer(art["model"]).shap_values(X)[0]
    factors = sorted(({"factor": CR.FEATURE_LABELS[f], "value": round(float(X.iloc[0][f]), 3), "shap": round(float(v), 3),
                       "effect": "raises risk" if v > 0 else "lowers risk"} for f, v in zip(CR.FEATURES, sv)), key=lambda d: -abs(d["shap"]))
    m = registry.metrics().get("credit_risk", {})
    return {"default_probability_pct": round(p * 100, 1), "risk_band": CR._band(p), "population_base_rate_pct": round(art["base_rate"] * 100, 1),
            "factors": factors, "months_used": len(body.months),
            "model": {"version": (registry.PV.active().get("credit_risk") or {}).get("version"),
                      "test_roc_auc": (m.get("test") or {}).get("xgboost", {}).get("roc_auc"),
                      "logistic_regression_roc_auc": (m.get("test") or {}).get("logistic_regression_baseline", {}).get("roc_auc")},
            "limitation": "Model-generated estimate from patterns in 30,000 Taiwanese card accounts (2005). It is not a credit-bureau "
                          "score and is not validated for Indian borrowers."}


@router.get("/models/lab", summary="Model Lab: status, provenance and metrics of every model (active, awaiting or benchmark)")
def model_lab():
    return registry.lab()


@router.post("/models/retrain", summary="Disabled: real-data training is a local, owner-approved step")
def retrain(request: Request, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    # Phase 6: models are trained only from approved real datasets on the owner's machine (python -m app.ml.train) and
    # loaded only after explicit activation. The API never trains, and never on synthetic data.
    raise HTTPException(410, "Retraining through the API was removed. Train locally with: python -m app.ml.train, "
                             "then activate an evaluated version: python -m app.ml.train activate <model> <version> --reason ...")

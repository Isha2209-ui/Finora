"""Statement import, review and intelligence.

    POST   /api/profiles/{id}/imports                    upload a CSV -> layout detection preview (nothing saved yet)
    GET    /api/profiles/{id}/imports                    import history
    GET    /api/profiles/{id}/imports/{imp}              status, live progress and outcome
    POST   /api/profiles/{id}/imports/{imp}/start        confirm mapping / statement kind / account -> runs in the background
    POST   /api/profiles/{id}/imports/{imp}/cancel       cancel a preview or a running import (nothing is kept)
    DELETE /api/profiles/{id}/imports/{imp}              undo a finished import (its rows removed, balance restored)
    GET    /api/profiles/{id}/review                     rows Finora is unsure about, grouped by counterparty
    POST   /api/profiles/{id}/review/classify            correct rows (category, income type or transfer); optionally remember
    POST   /api/profiles/{id}/review/confirm             accept rows as classified
    GET    /api/profiles/{id}/category-rules             remembered corrections;  DELETE .../category-rules/{rule}
    GET    /api/profiles/{id}/insights                   Statement Intelligence (works for every profile kind)

Every write needs profile_writer (own sandbox or private profile). Audit rows carry counts and ids, never narrations or amounts.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import ProfileCtx, audit, profile_reader, profile_writer, rate_limit
from ..config import UPLOAD_MAX_BYTES, UPLOAD_MAX_PER_HOUR
from ..database import get_db
from ..services import intelligence, statement_import as SI
from ..services.cleaning import ALL_CATEGORIES, standardise_category
from ..services.loader import load_identity
from ..services.statement_classify import INCOME_CLASSES, merchant_name
from ..services.statement_parser import StatementError
from . import common

router = APIRouter(prefix="/api", tags=["statements"])
READ_CHUNK = 1 << 20


def _imp(db: Session, ctx: ProfileCtx, imp_id: int) -> M.StatementImport:
    imp = db.get(M.StatementImport, imp_id)
    if imp is None or imp.user_id != ctx.profile.id:
        raise HTTPException(404, "Import not found.")
    return imp


async def read_limited(file: UploadFile, limit: int) -> bytes:
    """Stream the upload in 1 MB pieces and stop as soon as it exceeds the limit (never buffers more than limit + 1 MB)."""
    buf = bytearray()
    while True:
        part = await file.read(READ_CHUNK)
        if not part:
            return bytes(buf)
        buf += part
        if len(buf) > limit:
            raise HTTPException(413, f"File too large (limit {limit // 1_000_000} MB). Split the statement into smaller files.")


def _targets(db: Session, uid: int) -> dict:
    return {"accounts": [{"id": a.id, "label": f"{a.bank_name} {a.account_masked}", "balance": a.balance,
                          "balance_as_of": a.balance_as_of.isoformat() if a.balance_as_of else None,
                          "balance_source": a.balance_source or "manual"}
                         for a in db.scalars(select(M.BankAccount).where(M.BankAccount.user_id == uid))],
            "cards": [{"id": c.id, "label": f"{c.issuer} {c.card_name} ••{c.last4}"}
                      for c in db.scalars(select(M.CreditCard).where(M.CreditCard.user_id == uid))]}


# ---------------------------------------------------------------- imports
@router.post("/profiles/{internal_id}/imports", status_code=201, summary="Upload a statement CSV and preview what was detected")
async def create_import(request: Request, file: UploadFile = File(...), ctx: ProfileCtx = Depends(profile_writer),
                        db: Session = Depends(get_db)):
    rate_limit(f"upload:{ctx.account.id}", UPLOAD_MAX_PER_HOUR, 3600, "Too many uploads in the last hour.")
    try:
        content = await read_limited(file, UPLOAD_MAX_BYTES)
    except HTTPException:
        audit(db, "statement.preview", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, outcome="denied",
              detail={"reason": "too_large"})
        raise
    if not content.strip():
        raise HTTPException(422, "The file is empty.")
    name = Path(file.filename or "statement.csv").name
    try:
        imp = SI.create_preview(db, ctx.profile, ctx.account.id, content, name)
    except StatementError as e:
        audit(db, "statement.preview", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, outcome="failed")
        raise HTTPException(422, str(e))
    audit(db, "statement.preview", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id,
          detail={"import_id": imp.id, "rows": imp.rows_total, "bytes": imp.size_bytes})
    return {**SI.status(imp), "detection": imp.detection, "same_file_imported": SI.same_file_imports(db, imp),
            **_targets(db, ctx.profile.id)}


@router.get("/profiles/{internal_id}/imports", summary="Statement import history")
def list_imports(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    q = select(M.StatementImport).where(M.StatementImport.user_id == ctx.profile.id).order_by(M.StatementImport.id.desc()).limit(50)
    return {"items": [SI.status(i) for i in db.scalars(q)], **_targets(db, ctx.profile.id)}


@router.get("/profiles/{internal_id}/imports/{imp_id}", summary="Import status, progress and outcome")
def get_import(imp_id: int, ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    imp = _imp(db, ctx, imp_id)
    out = SI.status(imp)
    if imp.status == "preview":
        out.update(detection=imp.detection, same_file_imported=SI.same_file_imports(db, imp), **_targets(db, ctx.profile.id))
    return out


class NewAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_name: str = Field(min_length=2, max_length=60)
    last4: str = Field(pattern=r"^\d{4}$")
    account_type: str = Field("savings", pattern=r"^(savings|salary|current)$")
    balance: float | None = Field(None, ge=-1e9, le=1e10)


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement_kind: str | None = Field(None, pattern=r"^(bank|card)$")
    account_id: int | None = None
    card_id: int | None = None
    new_account: NewAccount | None = None
    mapping: dict[str, str | None] | None = None
    sign_convention: str | None = Field(None, pattern=r"^(negative_is_debit|positive_is_debit)$")
    date_format: str | None = Field(None, max_length=20)
    update_balance: bool = True
    allow_same_file: bool = False


@router.post("/profiles/{internal_id}/imports/{imp_id}/start", status_code=202, summary="Confirm the mapping and start the import")
def start_import(imp_id: int, body: StartIn, request: Request, background: BackgroundTasks, ctx: ProfileCtx = Depends(profile_writer),
                 db: Session = Depends(get_db)):
    imp = _imp(db, ctx, imp_id)
    if not (body.account_id or body.card_id or body.new_account):
        raise HTTPException(422, "Choose which account or card this statement belongs to (or create the account).")
    if SI.same_file_imports(db, imp) and not body.allow_same_file:
        raise HTTPException(409, "This exact file was already imported. Rows already present would be skipped anyway; "
                                 "set allow_same_file to import it again.")
    try:
        SI.configure(db, ctx.profile, imp, body.model_dump() | {"new_account": body.new_account.model_dump() if body.new_account else None})
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit(db, "statement.import", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id,
          detail={"import_id": imp.id, "kind": imp.statement_kind, "account_id": imp.account_id, "card_id": imp.card_id,
                  "new_account": bool(body.new_account), "mapping_changed": bool(body.mapping)})
    background.add_task(SI.run, imp.id)
    return SI.status(imp)


@router.post("/profiles/{internal_id}/imports/{imp_id}/cancel", summary="Cancel a preview or a running import")
def cancel_import(imp_id: int, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    imp = _imp(db, ctx, imp_id)
    try:
        SI.cancel(db, imp)
    except ValueError as e:
        raise HTTPException(409, str(e))
    audit(db, "statement.cancel", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, detail={"import_id": imp.id})
    db.refresh(imp)
    return SI.status(imp)


@router.delete("/profiles/{internal_id}/imports/{imp_id}", summary="Undo a finished import")
def undo_import(imp_id: int, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    imp = _imp(db, ctx, imp_id)
    try:
        res = SI.undo(db, imp)
    except ValueError as e:
        raise HTTPException(409, str(e))
    common.invalidate(ctx.profile.id)
    audit(db, "statement.undo", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id,
          detail={"import_id": imp.id, **res})
    return {**SI.status(imp), "undo": res}


# ---------------------------------------------------------------- review & corrections
def _labels(db: Session, uid: int) -> dict:
    acc = {a.id: f"{a.bank_name} {a.account_masked}" for a in db.scalars(select(M.BankAccount).where(M.BankAccount.user_id == uid))}
    cards = {c.id: f"{c.issuer} ••{c.last4}" for c in db.scalars(select(M.CreditCard).where(M.CreditCard.user_id == uid))}
    return {"acc": acc, "card": cards}


def _item_tx(t: M.Transaction, lab) -> dict:
    return {"kind": "tx", "id": t.id, "date": t.date.isoformat(), "description": t.raw_description, "amount": t.amount, "type": t.type,
            "merchant": t.merchant or merchant_name(t.raw_description), "classified_as": t.category, "category_source": t.category_source,
            "confidence": t.confidence, "reason": t.review_reason, "flags": t.flags, "import_id": t.import_id,
            "source": lab["card"].get(t.card_id) or lab["acc"].get(t.account_id) or "-"}


def _item_inc(r: M.IncomeRecord, lab) -> dict:
    return {"kind": "income", "id": r.id, "date": r.date.isoformat(), "description": r.raw_description or r.source, "amount": r.amount,
            "type": "credit", "merchant": merchant_name(r.raw_description or r.source), "classified_as": f"Income: {r.source}",
            "category_source": r.classified_by, "confidence": r.confidence, "reason": r.review_reason, "flags": None,
            "import_id": r.import_id, "source": lab["acc"].get(r.account_id) or "-"}


@router.get("/profiles/{internal_id}/review", summary="Rows that need your review, grouped by counterparty")
def review_queue(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db), import_id: int | None = None,
                 limit: int = Query(300, ge=1, le=2000)):
    uid, lab = ctx.profile.id, _labels(db, ctx.profile.id)
    qt = select(M.Transaction).where(M.Transaction.user_id == uid, M.Transaction.needs_review.is_(True))
    qi = select(M.IncomeRecord).where(M.IncomeRecord.user_id == uid, M.IncomeRecord.needs_review.is_(True))
    if import_id:
        qt, qi = qt.where(M.Transaction.import_id == import_id), qi.where(M.IncomeRecord.import_id == import_id)
    total = (db.scalar(select(func.count()).select_from(qt.subquery())) or 0) + (db.scalar(select(func.count()).select_from(qi.subquery())) or 0)
    items = [_item_tx(t, lab) for t in db.scalars(qt.order_by(M.Transaction.date.desc()).limit(limit))] + \
            [_item_inc(r, lab) for r in db.scalars(qi.order_by(M.IncomeRecord.date.desc()).limit(limit))]
    groups: dict[tuple, dict] = {}
    for it in items:
        key = (it["merchant"].upper(), it["type"], it["classified_as"])
        g = groups.setdefault(key, {"merchant": it["merchant"], "type": it["type"], "classified_as": it["classified_as"],
                                    "reason": it["reason"], "count": 0, "total": 0.0, "items": []})
        g["count"] += 1
        g["total"] = round(g["total"] + it["amount"], 2)
        g["items"].append(it)
    out = sorted(groups.values(), key=lambda g: (-g["count"], -g["total"]))
    return {"total": total, "groups": out, "categories": ALL_CATEGORIES, "income_types": INCOME_CLASSES}


class ItemRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=r"^(tx|income)$")
    id: int


class ClassifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ItemRef] = Field(min_length=1, max_length=2000)
    category: str | None = None          # spending / non-expense category (Transfer, Card Payment, Investment ...)
    income_type: str | None = None       # Salary, Other income, Interest ...
    remember: bool = False               # apply to future imports from the same counterparty
    apply_to_similar: bool = False       # also re-classify other rows from the same counterparty that still need review


def _load_items(db: Session, uid: int, refs: list[ItemRef]):
    tx_ids = [r.id for r in refs if r.kind == "tx"]
    inc_ids = [r.id for r in refs if r.kind == "income"]
    txs = db.scalars(select(M.Transaction).where(M.Transaction.id.in_(tx_ids), M.Transaction.user_id == uid)).all() if tx_ids else []
    incs = db.scalars(select(M.IncomeRecord).where(M.IncomeRecord.id.in_(inc_ids), M.IncomeRecord.user_id == uid)).all() if inc_ids else []
    if len(txs) != len(set(tx_ids)) or len(incs) != len(set(inc_ids)):
        raise HTTPException(404, "One or more rows were not found in this profile.")
    return list(txs), list(incs)


@router.post("/profiles/{internal_id}/review/classify", summary="Correct how rows are classified")
def classify_rows(body: ClassifyIn, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    uid = ctx.profile.id
    if bool(body.category) == bool(body.income_type):
        raise HTTPException(422, "Send either a category or an income_type.")
    cat = standardise_category(body.category) if body.category else None
    if cat and cat not in ALL_CATEGORIES:
        raise HTTPException(422, f"Unknown category. Choose one of: {', '.join(ALL_CATEGORIES)}")
    if body.income_type and body.income_type not in INCOME_CLASSES:
        raise HTTPException(422, f"Unknown income type. Choose one of: {', '.join(INCOME_CLASSES)}")
    txs, incs = _load_items(db, uid, body.items)
    if body.income_type and any(t.type != "credit" for t in txs):
        raise HTTPException(422, "Only credits (money coming in) can be classified as income.")
    keys = {merchant_name(t.raw_description).upper() for t in txs} | {merchant_name(r.raw_description or r.source).upper() for r in incs}
    if body.apply_to_similar:
        more_t = db.scalars(select(M.Transaction).where(M.Transaction.user_id == uid, M.Transaction.needs_review.is_(True))).all()
        more_i = db.scalars(select(M.IncomeRecord).where(M.IncomeRecord.user_id == uid, M.IncomeRecord.needs_review.is_(True))).all()
        seen_t, seen_i = {t.id for t in txs}, {r.id for r in incs}
        txs += [t for t in more_t if t.id not in seen_t and merchant_name(t.raw_description).upper() in keys
                and (not body.income_type or t.type == "credit")]
        incs += [r for r in more_i if r.id not in seen_i and merchant_name(r.raw_description or r.source).upper() in keys]
    moved = changed = 0
    for t in txs:
        if body.income_type:                                  # transaction -> income record
            db.add(M.IncomeRecord(user_id=uid, account_id=t.account_id, amount=t.amount, source=body.income_type, date=t.date,
                                  import_id=t.import_id, raw_description=t.raw_description, classified_by="user", confidence=1.0,
                                  needs_review=False))
            db.delete(t)
            moved += 1
        else:
            t.category, t.category_source, t.needs_review, t.review_reason, t.confidence = cat, "user", False, None, 1.0
            changed += 1
    for r in incs:
        if body.income_type:
            r.source, r.classified_by, r.needs_review, r.review_reason, r.confidence = body.income_type, "user", False, None, 1.0
            changed += 1
        else:                                                 # income record -> transaction (e.g. it was a transfer or a refund)
            n = db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.user_id == uid)) or 0
            db.add(M.Transaction(user_id=uid, account_id=r.account_id, card_id=None, ref=f"{ctx.profile.internal_id[-6:]}-R{r.id}-{n + 1}",
                                 date=r.date, amount=r.amount, type="credit", raw_description=(r.raw_description or r.source)[:200],
                                 category=cat, category_source="user", merchant=merchant_name(r.raw_description or r.source)[:80],
                                 import_id=r.import_id, confidence=1.0, needs_review=False,
                                 flags="refund" if cat not in ("Transfer", "Card Payment", "Investment") else None))
            db.delete(r)
            moved += 1
    rules = 0
    if body.remember:
        target = cat or body.income_type
        for k in keys:
            if not k:
                continue
            rule = db.scalar(select(M.CategoryRule).where(M.CategoryRule.user_id == uid, M.CategoryRule.merchant_key == k[:80]))
            if rule:
                rule.category = target
            else:
                db.add(M.CategoryRule(user_id=uid, merchant_key=k[:80], category=target))
            rules += 1
    db.commit()
    common.invalidate(uid)
    audit(db, "statement.review.classify", request=request, app_user_id=ctx.account.id, profile_id=uid,
          detail={"changed": changed, "moved": moved, "rules": rules, "to": cat or body.income_type})
    return {"changed": changed, "moved_between_income_and_spending": moved, "rules_saved": rules}


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ItemRef] = Field(min_length=1, max_length=2000)


@router.post("/profiles/{internal_id}/review/confirm", summary="Accept rows as classified")
def confirm_rows(body: ConfirmIn, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    txs, incs = _load_items(db, ctx.profile.id, body.items)
    for x in txs + incs:
        x.needs_review, x.review_reason = False, None
    db.commit()
    common.invalidate(ctx.profile.id)
    audit(db, "statement.review.confirm", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id,
          detail={"rows": len(txs) + len(incs)})
    return {"confirmed": len(txs) + len(incs)}


@router.get("/profiles/{internal_id}/category-rules", summary="Corrections remembered for future imports")
def list_rules(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    q = select(M.CategoryRule).where(M.CategoryRule.user_id == ctx.profile.id).order_by(M.CategoryRule.merchant_key)
    return [{"id": r.id, "merchant_key": r.merchant_key, "category": r.category, "created_at": r.created_at.isoformat()} for r in db.scalars(q)]


@router.delete("/profiles/{internal_id}/category-rules/{rule_id}", summary="Forget a remembered correction")
def delete_rule(rule_id: int, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    n = db.execute(delete(M.CategoryRule).where(M.CategoryRule.id == rule_id, M.CategoryRule.user_id == ctx.profile.id)).rowcount
    if not n:
        raise HTTPException(404, "Rule not found.")
    db.commit()
    audit(db, "statement.rule.delete", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, detail={"rule_id": rule_id})
    return {"deleted": rule_id}


# ---------------------------------------------------------------- intelligence
@router.get("/profiles/{internal_id}/insights", summary="Statement Intelligence: where money goes, trends, merchants, recurring, income")
def insights(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db), months: int | None = Query(None, ge=1, le=60),
             account_id: int | None = None, card_id: int | None = None):
    ident = load_identity(db, ctx.profile.id)
    if account_id is not None and not any(a["id"] == account_id for a in ident.accounts):
        raise HTTPException(404, "Account not found in this profile.")
    if card_id is not None and not any(c["id"] == card_id for c in ident.cards):
        raise HTTPException(404, "Card not found in this profile.")
    return intelligence.build(ident, months=months, account_id=account_id, card_id=card_id)

"""Create, read, update and delete every part of a financial identity (manual entry).

    GET    /api/records/schema                                  field definitions for all record types (form builder)
    GET    /api/profiles/{id}/records                           counts per record type
    GET    /api/profiles/{id}/records/{type}                    list
    POST   /api/profiles/{id}/records/{type}                    create
    PATCH  /api/profiles/{id}/records/{type}/{item_id}          update (validated as a whole record after merging)
    DELETE /api/profiles/{id}/records/{type}/{item_id}          delete (?cascade=true needed when other records depend on it)

Every write: ownership (profile_writer: own sandbox or private profile; templates are read-only), validation,
referenced records must belong to the same profile, audit row (record type + id + changed field NAMES - never
values), and the profile's analysis cache is invalidated so the next read recomputes everything.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import ProfileCtx, audit, profile_reader, profile_writer
from ..database import get_db
from ..ml import categoriser, registry
from ..records import RECORD_TYPES, RecordType, field_meta
from ..services.cleaning import standardise_category
from . import common

router = APIRouter(prefix="/api", tags=["Manual entry (records)"])

# What depends on a record, so a delete never silently removes or orphans other data.
DEPENDENTS = {
    "bank_accounts": [(M.Transaction, "account_id", "transactions"), (M.IncomeRecord, "account_id", "income records")],
    "credit_cards": [(M.Transaction, "card_id", "transactions"), (M.CardStatement, "card_id", "card statements")],
    "properties": [(M.Loan, "property_id", "loans secured on it")],
}


def _type(record_type: str) -> RecordType:
    rt = RECORD_TYPES.get(record_type)
    if rt is None:
        raise HTTPException(404, f"Unknown record type '{record_type}'. Use one of: {', '.join(RECORD_TYPES)}")
    return rt


def _out(rt: RecordType, row) -> dict:
    data = rt.from_db(row) if rt.from_db else {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key != "user_id"}
    return {**data, "_title": rt.title(row) if rt.title else str(row.id)}


def _own_row(db: Session, rt: RecordType, profile_id: int, item_id: int):
    row = db.get(rt.model, item_id)
    if row is None or row.user_id != profile_id:
        raise HTTPException(404, "Record not found.")
    return row


def _validate(rt: RecordType, data: dict) -> dict:
    try:
        return rt.schema(**data).model_dump()
    except ValidationError as e:
        raise HTTPException(422, "; ".join(f"{'.'.join(str(x) for x in err['loc']) or 'record'}: {err['msg'].removeprefix('Value error, ')}"
                                           for err in e.errors()))


def _check_refs(db: Session, rt: RecordType, profile_id: int, data: dict):
    for fld, model in rt.refs.items():
        ref = data.get(fld)
        if ref is not None and db.scalar(select(model.user_id).where(model.id == ref)) != profile_id:
            raise HTTPException(422, f"{fld}: that record does not belong to this profile.")


def _api_view(rt: RecordType, row) -> dict:
    """The current row expressed in API field names (what PATCH merges onto)."""
    d = _out(rt, row)
    return {k: d.get(k) for k in rt.schema.model_fields}


def _apply_category(rt: RecordType, data: dict) -> dict:
    """Transactions without a category are categorised by the same ML model used for statement uploads."""
    if rt.key != "transactions":
        return data
    if data.get("category"):
        data["category"] = standardise_category(data["category"])
        data["category_source"] = "user"
    else:
        p = categoriser.predict(registry.get("categoriser"), [data["description"]])[0]
        data["category"], data["category_source"] = p["category"], "model"
    return data


def _changed(rt: RecordType, data: dict, profile_id: int, request: Request, ctx: ProfileCtx, db: Session, action: str,
             item_id: int, fields: list[str] | None = None):
    common.invalidate(profile_id)
    audit(db, f"record.{action}", request=request, app_user_id=ctx.account.id, profile_id=profile_id,
          detail={"type": rt.key, "id": item_id, **({"fields": sorted(fields)} if fields else {})})


# ---------------------------------------------------------------- schema
@router.get("/records/schema", summary="Field definitions of every record type (drives the entry forms)")
def schema():
    return [{"type": t.key, "label": t.label, "group": t.group, "affects": t.affects, "fields": field_meta(t.schema)}
            for t in RECORD_TYPES.values()]


# ---------------------------------------------------------------- read
@router.get("/profiles/{internal_id}/records", summary="How many records of each type this profile has")
def counts(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    return {k: db.scalar(select(func.count()).select_from(t.model).where(t.model.user_id == ctx.profile.id)) or 0
            for k, t in RECORD_TYPES.items()}


@router.get("/profiles/{internal_id}/records/{record_type}", summary="List records of one type")
def list_records(record_type: str, limit: int = Query(500, ge=1, le=2000), offset: int = Query(0, ge=0),
                 ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    rt = _type(record_type)
    q = select(rt.model).where(rt.model.user_id == ctx.profile.id)
    order = rt.model.date.desc() if hasattr(rt.model, "date") else rt.model.id
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(order, rt.model.id.desc()).limit(limit).offset(offset)).all()
    return {"type": rt.key, "total": total, "items": [_out(rt, r) for r in rows], "read_only": ctx.profile.kind == "template"}


# ---------------------------------------------------------------- write
@router.post("/profiles/{internal_id}/records/{record_type}", summary="Add a record", status_code=201)
def create(record_type: str, body: dict, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    rt = _type(record_type)
    data = _validate(rt, body)
    _check_refs(db, rt, ctx.profile.id, data)
    data = _apply_category(rt, data)
    if rt.key == "transactions":
        data["ref"] = f"{ctx.profile.internal_id[-6:]}-M{secrets.token_hex(4).upper()}"
    if rt.key == "bank_accounts" and data.get("is_primary"):
        db.execute(update(M.BankAccount).where(M.BankAccount.user_id == ctx.profile.id).values(is_primary=False))
    row = rt.model(user_id=ctx.profile.id, **(rt.to_db(data) if rt.to_db else data))
    db.add(row)
    db.flush()
    _changed(rt, data, ctx.profile.id, request, ctx, db, "create", row.id)
    db.refresh(row)
    return _out(rt, row)


@router.patch("/profiles/{internal_id}/records/{record_type}/{item_id}", summary="Change a record")
def patch(record_type: str, item_id: int, body: dict, request: Request, ctx: ProfileCtx = Depends(profile_writer),
          db: Session = Depends(get_db)):
    rt = _type(record_type)
    row = _own_row(db, rt, ctx.profile.id, item_id)
    unknown = set(body) - set(rt.schema.model_fields)
    if unknown:
        raise HTTPException(422, f"Unknown field(s): {', '.join(sorted(unknown))}")
    current = _api_view(rt, row)
    merged = _validate(rt, {**{k: v for k, v in current.items() if v is not None}, **body})
    _check_refs(db, rt, ctx.profile.id, merged)
    changed = [k for k in body if merged.get(k) != current.get(k)]
    if rt.key == "transactions":
        if "category" in body:
            merged = _apply_category(rt, merged)
        elif "description" in body and row.category_source == "model":
            merged["category"] = None
            merged = _apply_category(rt, merged)            # re-predict a model-assigned category for the new text
        else:
            merged["category"] = row.category
    if rt.key == "bank_accounts" and merged.get("is_primary") and not row.is_primary:
        db.execute(update(M.BankAccount).where(M.BankAccount.user_id == ctx.profile.id).values(is_primary=False))
    for k, v in (rt.to_db(merged) if rt.to_db else merged).items():
        setattr(row, k, v)
    if rt.key == "bank_accounts" and "balance" in changed:
        row.balance_source, row.balance_as_of = "manual", None     # a typed balance is no longer the statement's verified one
    if rt.key == "transactions" and "category" in changed:
        row.category_source, row.needs_review, row.review_reason = "user", False, None
    _changed(rt, merged, ctx.profile.id, request, ctx, db, "update", row.id, changed)
    db.refresh(row)
    return _out(rt, row)


@router.delete("/profiles/{internal_id}/records/{record_type}/{item_id}", summary="Delete a record")
def remove(record_type: str, item_id: int, request: Request, cascade: bool = False, ctx: ProfileCtx = Depends(profile_writer),
           db: Session = Depends(get_db)):
    rt = _type(record_type)
    row = _own_row(db, rt, ctx.profile.id, item_id)
    deps = [(model, fld, label, db.scalar(select(func.count()).select_from(model).where(getattr(model, fld) == row.id)) or 0)
            for model, fld, label in DEPENDENTS.get(rt.key, [])]
    deps = [d for d in deps if d[3]]
    if deps and not cascade:
        raise HTTPException(409, "This record is linked to " + ", ".join(f"{n} {label}" for *_, label, n in deps)
                            + ". Delete again with cascade=true to remove them too (loans are only unlinked).")
    removed = {}
    for model, fld, label, n in deps:
        if model is M.Loan:  # never delete a loan because its property was removed; just unlink it
            db.execute(update(M.Loan).where(M.Loan.property_id == row.id).values(property_id=None))
        else:
            db.execute(delete(model).where(getattr(model, fld) == row.id))
        removed[label] = n
    if rt.key == "bank_accounts":
        for imp in db.scalars(select(M.StatementImport).where(M.StatementImport.user_id == ctx.profile.id,
                                                              M.StatementImport.account_id == row.id)):
            imp.account_id = None
            if (imp.summary or {}).get("created_account_id") == row.id:
                imp.summary = {**imp.summary, "created_account_id": None}
    db.delete(row)
    _changed(rt, {}, ctx.profile.id, request, ctx, db, "delete", item_id)
    return {"deleted": item_id, "type": rt.key, "also_removed": removed}

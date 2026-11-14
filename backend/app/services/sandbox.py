"""Demo sandboxes: an editable, expiring copy of a read-only demo template, owned by one account.

"Explore demo identity" never shows the template itself. It copies every source row of the template (accounts, cards,
statements, transactions, income, holdings, loans, goals, history ...) into a new profile with kind="sandbox",
owner_id=<account> and expires_at=now+SANDBOX_TTL_HOURS. All edits go to the copy, so the four templates can never be
changed through the application. Derived rows (analysis results, recommendations, reports, chat) are not copied - they
are recomputed for the sandbox.

Reset deletes the sandbox's rows and copies the template again under the same profile ID.
Expired sandboxes are unreachable at once (auth.can_read) and physically deleted by purge_expired().
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from .. import models as M
from ..config import SANDBOX_TTL_HOURS
from .profile_ops import delete_profile_data

# Parents first: their new IDs are needed to remap foreign keys in the children.
_PARENTS = [("account_id", M.BankAccount), ("card_id", M.CreditCard), ("property_id", M.Property)]
_CHILDREN = [M.Transaction, M.IncomeRecord, M.RecurringPayment, M.StockHolding, M.MutualFundHolding, M.SIP, M.FixedDeposit,
             M.OtherAsset, M.Loan, M.InsurancePolicy, M.Goal, M.SavingsRecord, M.MonthlySummary, M.NetWorthSnapshot]
_PROFILE_FIELDS = ["name", "age", "occupation", "employment_type", "city", "retirement_age_target", "archetype", "pan_masked"]


def _row(obj, skip=("id",)) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in skip}


def _copy_rows(db: Session, src_id: int, dst_id: int) -> int:
    n = 0
    remap: dict[str, dict[int, int]] = {}
    for fk, model in _PARENTS:
        remap[fk] = {}
        for r in db.scalars(select(model).where(model.user_id == src_id).order_by(model.id)).all():
            data = _row(r)
            data["user_id"] = dst_id
            data.pop("uid", None)                       # every copy gets its own immutable uid
            new = model(**data)
            db.add(new)
            db.flush()
            remap[fk][r.id] = new.id
            n += 1
    # card statements hang off cards, not users
    if remap["card_id"]:
        rows = db.scalars(select(M.CardStatement).where(M.CardStatement.card_id.in_(list(remap["card_id"])))).all()
        payload = [{**_row(r), "card_id": remap["card_id"][r.card_id]} for r in rows]
        if payload:
            db.execute(insert(M.CardStatement), payload)
            n += len(payload)
    for model in _CHILDREN:
        rows = db.scalars(select(model).where(model.user_id == src_id).order_by(model.id)).all()
        payload = []
        for r in rows:
            data = _row(r)
            data["user_id"] = dst_id
            for fk, ids in remap.items():
                if fk in data and data[fk] is not None:
                    data[fk] = ids.get(data[fk])
            payload.append(data)
        if payload:
            db.execute(insert(model), payload)  # bulk insert: transactions are the bulk of the rows
            n += len(payload)
    return n


def _new_id(db: Session) -> str:
    while True:
        iid = f"SB_{secrets.token_hex(8).upper()}"
        if not db.scalar(select(M.User.id).where(M.User.internal_id == iid)):
            return iid


def find_active(db: Session, template: M.User, owner_id: int) -> M.User | None:
    return db.scalar(select(M.User).where(M.User.kind == "sandbox", M.User.owner_id == owner_id,
                                          M.User.template_id == template.id, M.User.expires_at > datetime.utcnow()))


def clone(db: Session, template: M.User, owner_id: int, internal_id: str | None = None) -> tuple[M.User, int]:
    """Copy a template into a new sandbox owned by `owner_id`. Caller commits."""
    if template.kind != "template":
        raise ValueError("Only demo templates can be explored as a sandbox.")
    sb = M.User(internal_id=internal_id or _new_id(db), kind="sandbox", owner_id=owner_id, template_id=template.id,
                expires_at=datetime.utcnow() + timedelta(hours=SANDBOX_TTL_HOURS), is_demo=True, pan_hash=None,
                **{f: getattr(template, f) for f in _PROFILE_FIELDS})
    db.add(sb)
    db.flush()
    return sb, _copy_rows(db, template.id, sb.id)


def open_for(db: Session, template: M.User, owner_id: int) -> tuple[M.User, bool]:
    """The account's active sandbox of this template, creating one if needed. Returns (sandbox, created)."""
    existing = find_active(db, template, owner_id)
    if existing:
        return existing, False
    sb, _ = clone(db, template, owner_id)
    db.commit()
    return sb, True


def reset(db: Session, sandbox: M.User) -> M.User:
    """Throw away every change: delete the sandbox and copy the template again under the same ID and a fresh expiry."""
    if sandbox.kind != "sandbox" or sandbox.template_id is None:
        raise ValueError("Only demo sandboxes can be reset.")
    template = db.get(M.User, sandbox.template_id)
    iid, owner = sandbox.internal_id, sandbox.owner_id
    delete_profile_data(db, sandbox)
    db.flush()
    sb, _ = clone(db, template, owner, internal_id=iid)
    db.commit()
    return sb


def purge_expired(db: Session) -> int:
    """Physically delete sandboxes past their expiry. Returns how many were removed."""
    expired = db.scalars(select(M.User).where(M.User.kind == "sandbox", M.User.expires_at <= datetime.utcnow())).all()
    for sb in expired:
        delete_profile_data(db, sb)
    if expired:
        db.commit()
    return len(expired)

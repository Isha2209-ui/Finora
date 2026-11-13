"""Loads one person's complete financial identity from the database."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M


def _rows(db: Session, model, uid: int, **filters) -> list[dict]:
    q = select(model).where(model.user_id == uid)
    out = []
    for r in db.scalars(q).all():
        out.append({c.name: getattr(r, c.name) for c in model.__table__.columns})
    return out


@dataclass
class Identity:
    user: dict
    accounts: list[dict]
    cards: list[dict]
    card_statements: list[dict]
    income: pd.DataFrame
    transactions: pd.DataFrame
    recurring: list[dict]
    stocks: list[dict]
    mfs: list[dict]
    sips: list[dict]
    fds: list[dict]
    properties: list[dict]
    other_assets: list[dict]
    loans: list[dict]
    insurance: list[dict]
    goals: list[dict]
    monthly: list[dict]
    net_worth_history: list[dict]

    @property
    def uid(self) -> int:
        return self.user["id"]


def load_identity(db: Session, uid: int) -> Identity:
    user = db.get(M.User, uid)
    if user is None:
        raise KeyError(uid)
    u = {c.name: getattr(user, c.name) for c in M.User.__table__.columns if c.name != "pan_hash"}
    cards = _rows(db, M.CreditCard, uid)
    card_ids = [c["id"] for c in cards]
    stmts = []
    if card_ids:
        for r in db.scalars(select(M.CardStatement).where(M.CardStatement.card_id.in_(card_ids))).all():
            stmts.append({c.name: getattr(r, c.name) for c in M.CardStatement.__table__.columns})
    tx = pd.DataFrame(_rows(db, M.Transaction, uid))
    if tx.empty:
        tx = pd.DataFrame(columns=[c.name for c in M.Transaction.__table__.columns])
    inc = pd.DataFrame(_rows(db, M.IncomeRecord, uid))
    if inc.empty:
        inc = pd.DataFrame(columns=["amount", "source", "date", "account_id"])
    return Identity(
        user=u, accounts=_rows(db, M.BankAccount, uid), cards=cards, card_statements=stmts, income=inc,
        transactions=tx, recurring=_rows(db, M.RecurringPayment, uid), stocks=_rows(db, M.StockHolding, uid),
        mfs=_rows(db, M.MutualFundHolding, uid), sips=_rows(db, M.SIP, uid), fds=_rows(db, M.FixedDeposit, uid),
        properties=_rows(db, M.Property, uid), other_assets=_rows(db, M.OtherAsset, uid), loans=_rows(db, M.Loan, uid),
        insurance=_rows(db, M.InsurancePolicy, uid), goals=_rows(db, M.Goal, uid),
        monthly=sorted(_rows(db, M.MonthlySummary, uid), key=lambda r: r["month"]),
        net_worth_history=sorted(_rows(db, M.NetWorthSnapshot, uid), key=lambda r: r["month"]),
    )

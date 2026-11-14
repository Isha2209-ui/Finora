"""Bulk-loads the TRAINING population from the database.

Only profiles with kind == "population" (the synthetic training population created by the seed script) are used.
Demo templates, sandboxes and - most importantly - private profiles built by real account holders are never
used for training.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..data.generator import DISCRETIONARY, ESSENTIAL, NON_EXPENSE


def load(db: Session) -> dict:
    bind = db.get_bind()
    users = pd.read_sql(select(M.User.id, M.User.age, M.User.archetype, M.User.city, M.User.employment_type)
                        .where(M.User.kind == "population"), bind)
    ids = users["id"].tolist()
    tx = pd.read_sql(select(M.Transaction.id, M.Transaction.user_id, M.Transaction.account_id, M.Transaction.card_id,
                            M.Transaction.date, M.Transaction.amount, M.Transaction.type, M.Transaction.category,
                            M.Transaction.injected_anomaly_label).where(M.Transaction.user_id.in_(ids)), bind)
    inc = pd.read_sql(select(M.IncomeRecord.user_id, M.IncomeRecord.amount, M.IncomeRecord.date)
                      .where(M.IncomeRecord.user_id.in_(ids)), bind)
    cards = pd.read_sql(select(M.CreditCard.user_id, M.CreditCard.credit_limit, M.CreditCard.outstanding)
                        .where(M.CreditCard.user_id.in_(ids)), bind)
    loans = pd.read_sql(select(M.Loan.user_id, M.Loan.emi).where(M.Loan.user_id.in_(ids)), bind)
    tx["date"] = pd.to_datetime(tx["date"])
    inc["date"] = pd.to_datetime(inc["date"])
    return {"users": users, "transactions": tx, "income": inc, "cards": cards, "loans": loans,
            "monthly": monthly_panel(tx, inc)}


def monthly_panel(tx: pd.DataFrame, inc: pd.DataFrame) -> pd.DataFrame:
    """One row per (user, month) with the same definitions as services.calculations.monthly_frame."""
    t = tx.copy()
    t["month"] = pd.to_datetime(t["date"]).dt.to_period("M").astype(str)
    sign = t["type"].map({"credit": -1.0}).fillna(1.0)
    t["spend"] = (t["amount"] * sign).where(~t["category"].isin(NON_EXPENSE), 0.0)
    key = ["user_id", "month"]
    out = t.groupby(key)["spend"].sum().rename("expenses").to_frame()
    out["essential"] = t[t["category"].isin(ESSENTIAL)].groupby(key)["spend"].sum()
    out["discretionary"] = t[t["category"].isin(DISCRETIONARY)].groupby(key)["spend"].sum()
    out["emi"] = t[t["category"] == "EMI"].groupby(key)["spend"].sum()
    out["invested"] = t[t["category"] == "Investment"].groupby(key)["amount"].sum()
    out["txn_count"] = t[t["spend"] > 0].groupby(key)["spend"].count()
    i = inc.copy()
    i["month"] = pd.to_datetime(i["date"]).dt.to_period("M").astype(str)
    out["income"] = i.groupby(key)["amount"].sum()
    out = out.fillna(0.0).reset_index()
    out["savings"] = out["income"] - out["expenses"]
    return out.sort_values(key).reset_index(drop=True)

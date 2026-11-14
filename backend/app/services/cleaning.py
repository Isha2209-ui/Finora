"""Data-cleaning pipeline applied before every analysis (and to uploaded statements).

Rules (documented so they can be explained and tested):
  * Exact duplicate rows (same date, amount, description, account/card) are removed.
  * Rows with a missing/invalid date or amount are dropped; amounts are made positive and
    the direction is kept in `type` (debit | credit).
  * Category names are standardised (e.g. "Food" -> "Dining", "Bills" -> "Utilities").
  * Refunds (credits with a spending category) REDUCE that category's spend.
  * Own-account transfers, credit-card bill payments and investments are NOT expenses
    (counting card bills would double-count card spending).
  * Cash withdrawals are an expense in their own "Cash" category (use is unknown).
  * One-time large spends are flagged (>= 4x the category median and >= Rs 15,000).
  * Recurring payments are detected (same merchant in >= 3 months, amount within +/-10%).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..data.generator import DISCRETIONARY, ESSENTIAL, NON_EXPENSE

CATEGORY_SYNONYMS = {
    "food": "Dining", "restaurant": "Dining", "restaurants": "Dining", "eating out": "Dining", "dining": "Dining",
    "grocery": "Groceries", "groceries": "Groceries", "supermarket": "Groceries",
    "bills": "Utilities", "bill": "Utilities", "utility": "Utilities", "utilities": "Utilities", "electricity": "Utilities",
    "mobile": "Utilities", "internet": "Utilities", "shopping": "Shopping", "apparel": "Shopping",
    "travel": "Travel", "transport": "Travel", "cab": "Travel", "fuel": "Fuel", "petrol": "Fuel",
    "entertainment": "Entertainment", "movies": "Entertainment", "subscription": "Subscriptions",
    "subscriptions": "Subscriptions", "health": "Health", "medical": "Health", "pharmacy": "Health",
    "education": "Education", "insurance": "Insurance", "rent": "Rent", "emi": "EMI", "loan": "EMI",
    "investment": "Investment", "sip": "Investment", "mutual fund": "Investment", "transfer": "Transfer",
    "self transfer": "Transfer", "card payment": "Card Payment", "credit card payment": "Card Payment",
    "cash": "Cash", "atm": "Cash",
}
UNCATEGORISED = "Uncategorised"   # derived label only; never stored, never a choice in ALL_CATEGORIES
ALL_CATEGORIES = sorted(ESSENTIAL | DISCRETIONARY | NON_EXPENSE | {"EMI", "Cash"})


def standardise_category(c) -> str | None:
    if c is None or (isinstance(c, float) and np.isnan(c)):
        return None
    s = str(c).strip()
    if s in ALL_CATEGORIES:
        return s
    return CATEGORY_SYNONYMS.get(s.lower(), s.title())


def clean_transactions(tx: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report = {"rows_in": int(len(tx))}
    t = tx.copy()
    t["date"] = pd.to_datetime(t["date"], errors="coerce")
    t["amount"] = pd.to_numeric(t["amount"], errors="coerce")
    missing = t["date"].isna() | t["amount"].isna()
    report["dropped_missing_date_or_amount"] = int(missing.sum())
    t = t[~missing]
    if "type" not in t:
        t["type"] = np.where(t["amount"] < 0, "credit", "debit")
    t["type"] = t["type"].fillna("debit").str.lower().replace({"dr": "debit", "cr": "credit"})
    t["amount"] = t["amount"].abs()
    # A stored row's `ref` is unique, so two identical purchases on the same day (two metro recharges) are two rows and
    # both count. Without a ref (raw input, tests) identical rows are treated as one accidental duplicate.
    key = [c for c in ["date", "amount", "raw_description", "account_id", "card_id", "type", "ref"] if c in t.columns]
    dup = t.duplicated(subset=key, keep="first")
    report["duplicates_removed"] = int(dup.sum())
    t = t[~dup]
    if "category" in t:
        t["category"] = t["category"].map(standardise_category)
    if "category" not in t:
        t["category"] = None
    # No category (e.g. no approved categoriser, or a low-confidence row awaiting review): an explicit "Uncategorised" bucket in
    # this DERIVED frame (stored rows are untouched). An uncategorised debit is still money spent; an uncategorised credit is
    # NOT assumed to be a refund (it could be income or a transfer), so it neither reduces nor adds to spending.
    uncat = t["category"].isna()
    report["uncategorised"] = int(uncat.sum())
    t["category"] = t["category"].where(~uncat, UNCATEGORISED)
    t["month"] = t["date"].dt.to_period("M").astype(str)
    # signed spend contribution
    t["spend"] = np.where(t["category"].isin(NON_EXPENSE) | (uncat & (t["type"] == "credit")), 0.0,
                          np.where(t["type"] == "credit", -t["amount"], t["amount"]))
    t["is_refund"] = (t["type"] == "credit") & (~t["category"].isin(NON_EXPENSE)) & ~uncat
    report["refunds"] = int(t["is_refund"].sum())
    report["non_expense_rows"] = int(t["category"].isin(NON_EXPENSE).sum())
    # one-time large spends
    debit = t[(t["type"] == "debit") & (~t["category"].isin(NON_EXPENSE | {"Rent", "EMI"}))]
    med = debit.groupby("category")["amount"].transform("median")
    big = debit.index[(debit["amount"] >= 4 * med) & (debit["amount"] >= 15000)]
    t["is_one_time_large"] = t.index.isin(big)
    report["one_time_large_flagged"] = int(len(big))
    t = t.sort_values("date").reset_index(drop=True)
    report["rows_out"] = int(len(t))
    return t, report


_TOKEN = re.compile(r"[A-Z]{3,}")


def merchant_key(desc: str, merchant: str | None = None) -> str:
    if merchant:
        return str(merchant).upper()
    toks = [w for w in _TOKEN.findall(str(desc).upper()) if w not in {"UPI", "POS", "NEFT", "IMPS", "ACH", "NACH", "PAYMENT", "INDIA", "LTD", "PVT"}]
    return " ".join(toks[:2]) or str(desc)[:20]


def detect_recurring(t: pd.DataFrame, min_months: int = 3, tol: float = 0.10) -> list[dict]:
    d = t[t["type"] == "debit"].copy()
    if d.empty:
        return []
    d["mkey"] = [merchant_key(a, b) for a, b in zip(d["raw_description"], d.get("merchant", [None] * len(d)))]
    out = []
    for (mk, cat), g in d.groupby(["mkey", "category"]):
        monthly = g.groupby("month")["amount"].sum()
        if len(monthly) < min_months:
            continue
        med = monthly.median()
        if med <= 0:
            continue
        stable = ((monthly - med).abs() <= tol * med).mean()
        if stable >= 0.7 and len(g) <= len(monthly) * 1.5:
            out.append({"merchant": mk.title(), "category": cat, "typical_amount": round(float(med), 2),
                        "months_seen": int(len(monthly)), "stability_pct": round(float(stable) * 100, 1)})
    return sorted(out, key=lambda r: -r["typical_amount"])

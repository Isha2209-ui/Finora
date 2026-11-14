"""MoneyVis (one real UK current account, CC BY 4.0): raw .xlsx -> clean transactions -> monthly cash flows.

Cleaning decisions (each documented in the provenance record):
  * Empty spreadsheet rows (no date) are dropped.
  * 2,816 date cells are Excel serial numbers produced by an Excel day/month mix-up (e.g. serial 44902 = 6 Dec 2022, after the
    dataset ends). Converting the serial and swapping day and month restores them; this is proven by the result: every date is
    then non-increasing in transaction number (0 order violations, versus 149 without the swap). Text dates are dd/mm/yyyy.
  * Spending = debits EXCEPT money moved rather than spent: categories Savings, Investment, Account transfer, Safety Deposit
    Return. Income = credits in Paycheck, Supplementary Income, Interest, Travel Reimbursement.
  * The first (Jul 2015) and last (Jul 2022) months are partial and are dropped, never filled in.
"""
from __future__ import annotations

import pandas as pd

from ...config import DATASETS_DIR
from .xlsx import read_first_sheet

RAW = DATASETS_DIR / "raw" / "moneyvis" / "laramee26openBankTransactionData.xlsx"
PROCESSED = DATASETS_DIR / "processed" / "moneyvis"
NOT_SPENDING = {"Savings", "Investment", "Account transfer", "Safety Deposit Return"}
INCOME = {"Paycheck", "Supplementary Income", "Interest", "Travel Reimbursement"}


def transactions() -> tuple[pd.DataFrame, dict]:
    rows = read_first_sheet(RAW)
    hdr = rows[0]
    df = pd.DataFrame([r + [None] * (len(hdr) - len(r)) for r in rows[1:]], columns=hdr)
    n_raw = len(df)
    df = df.dropna(subset=["Transaction Date"]).copy()
    txt = pd.to_datetime(df["Transaction Date"], format="%d/%m/%Y", errors="coerce")
    serial = pd.to_datetime(pd.to_numeric(df["Transaction Date"].where(txt.isna()), errors="coerce"), unit="D", origin="1899-12-30")
    swapped = pd.to_datetime(dict(year=serial.dt.year, month=serial.dt.day, day=serial.dt.month), errors="coerce")
    df["date"] = txt.fillna(swapped)
    df["number"] = pd.to_numeric(df["Transaction Number"], errors="coerce")
    for src, dst in (("Debit Amount", "debit"), ("Credit Amount", "credit"), ("Balance", "balance")):
        df[dst] = pd.to_numeric(df[src], errors="coerce")
    df = df.sort_values("number").reset_index(drop=True)
    violations = int((df["date"].diff() > pd.Timedelta(0)).sum())
    out = pd.DataFrame({"number": df["number"], "date": df["date"], "type": df["Transaction Type"], "description": df["Transaction Description"],
                        "debit": df["debit"].fillna(0.0), "credit": df["credit"].fillna(0.0), "balance": df["balance"],
                        "category": df["Category"].fillna("Uncategorised").str.strip()})
    report = {"raw_rows": n_raw, "empty_rows_dropped": n_raw - len(df), "transactions": int(len(out)),
              "serial_dates_corrected": int(serial.notna().sum()), "date_order_violations_after_correction": violations,
              "date_from": out["date"].min().date().isoformat(), "date_to": out["date"].max().date().isoformat(),
              "duplicates": int(out.drop(columns="number").duplicated().sum()), "duplicate_treatment": "kept (separate bank rows)"}
    return out, report


def monthly(tx: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    t = tx.copy()
    t["month"] = t["date"].dt.to_period("M").astype(str)
    spend = t[~t["category"].isin(NOT_SPENDING)]
    inc = t[t["category"].isin(INCOME)]
    months = sorted(t["month"].unique())
    first, last = months[0], months[-1]
    full = [m for m in months if m not in (first, last)]
    idx = pd.period_range(full[0], full[-1], freq="M").astype(str)
    m = pd.DataFrame({"month": idx})
    m["expenses"] = m["month"].map(spend.groupby("month")["debit"].sum()).fillna(0.0)
    m["income"] = m["month"].map(inc.groupby("month")["credit"].sum()).fillna(0.0)
    m["txn_count"] = m["month"].map(spend[spend["debit"] > 0].groupby("month").size()).fillna(0).astype(int)
    m["discretionary"], m["emi"] = 0.0, 0.0           # not used by the real model's features
    gaps = [x for x in idx if x not in set(months)]
    return m, {"months_used": len(m), "partial_months_dropped": [first, last], "months_without_transactions": gaps,
               "missing_month_treatment": "a month with no spending rows counts as 0 spending (genuinely no activity on the account)"}

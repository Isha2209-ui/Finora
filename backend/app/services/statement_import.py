"""Import a bank / card statement CSV: detect columns, clean, categorise with the ML model, insert.

Accepted layouts (column names are matched loosely, any order):
  date | description/narration/particulars/details | amount [+ type or Dr/Cr]
  date | description | debit/withdrawal | credit/deposit
Dates may be DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD or "05 Oct 2026".
"""
from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..ml import categoriser, registry
from .cleaning import standardise_category

DATE_COLS = ["date", "txn date", "transaction date", "value date", "posting date", "tran date"]
DESC_COLS = ["description", "narration", "particulars", "details", "transaction details", "remarks", "transaction remarks"]
AMOUNT_COLS = ["amount", "transaction amount", "amount (inr)", "amt"]
DEBIT_COLS = ["debit", "withdrawal", "withdrawal amt", "withdrawal amt.", "debit amount", "dr", "withdrawals"]
CREDIT_COLS = ["credit", "deposit", "deposit amt", "deposit amt.", "credit amount", "cr", "deposits"]
TYPE_COLS = ["type", "dr/cr", "cr/dr", "txn type", "transaction type"]
CAT_COLS = ["category"]


def _find(cols: dict, names: list[str]):
    for n in names:
        if n in cols:
            return cols[n]
    return None


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[₹,\s]|INR|Rs\.?", "", regex=True).str.replace(r"\((.*)\)", r"-\1", regex=True), errors="coerce")


def parse_csv(content: bytes) -> tuple[pd.DataFrame, dict]:
    text = content.decode("utf-8-sig", errors="replace")
    # skip bank header junk: start at the first line that looks like a header row
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines[:40]) if any(d in l.lower() for d in DATE_COLS) and "," in l), 0)
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])), dtype=str, skip_blank_lines=True, on_bad_lines="skip")
    cols = {c.strip().lower(): c for c in df.columns}
    dc, xc = _find(cols, DATE_COLS), _find(cols, DESC_COLS)
    if dc is None or xc is None:
        raise ValueError("Could not find a date column and a description/narration column. "
                         f"Columns found: {', '.join(df.columns)}")
    out = pd.DataFrame({"date": pd.to_datetime(df[dc].str.strip(), errors="coerce", dayfirst=True, format="mixed"),
                        "raw_description": df[xc].astype(str).str.strip()})
    ac, dbc, crc, tc = _find(cols, AMOUNT_COLS), _find(cols, DEBIT_COLS), _find(cols, CREDIT_COLS), _find(cols, TYPE_COLS)
    if dbc is not None or crc is not None:
        deb = _num(df[dbc]).fillna(0) if dbc is not None else 0
        cre = _num(df[crc]).fillna(0) if crc is not None else 0
        out["amount"] = (deb if dbc is not None else 0) + (cre if crc is not None else 0)
        out["type"] = ["credit" if (c if crc is not None else 0) and c > 0 and not (d if dbc is not None else 0) else "debit"
                       for d, c in zip(deb if dbc is not None else [0] * len(df), cre if crc is not None else [0] * len(df))]
    elif ac is not None:
        amt = _num(df[ac])
        if tc is not None:
            typ = df[tc].astype(str).str.strip().str.lower().map(lambda v: "credit" if str(v).startswith("c") else "debit")
        else:
            typ = amt.map(lambda v: "credit" if v is not None and v < 0 else "debit")
        out["amount"], out["type"] = amt.abs(), typ
    else:
        raise ValueError("Could not find an amount column (amount, or debit/credit).")
    cc = _find(cols, CAT_COLS)
    out["category"] = df[cc].map(standardise_category) if cc is not None else None
    n_in = len(out)
    out = out.dropna(subset=["date", "amount"])
    out = out[(out["amount"] > 0) & (out["raw_description"].str.len() > 1)]
    out = out.drop_duplicates(subset=["date", "amount", "raw_description", "type"])
    report = {"rows_in_file": int(n_in), "rows_valid": int(len(out)), "rows_dropped": int(n_in - len(out)),
              "layout": "debit/credit columns" if dbc is not None or crc is not None else "single amount column"}
    return out.reset_index(drop=True), report


INCOME_HINTS = ("SALARY", "NEFT CR", "INTEREST", "REFUND", "CASHBACK", "DIVIDEND", "IMPS CR", "CREDIT INTEREST")


def import_statement(db: Session, user: M.User, content: bytes, account_id: int | None = None, card_id: int | None = None) -> dict:
    df, report = parse_csv(content)
    if df.empty:
        raise ValueError("No valid transactions found in the file.")
    need = df["category"].isna()
    preds = categoriser.predict(registry.get("categoriser"), df.loc[need, "raw_description"].tolist())
    conf = [None] * len(df)
    for (idx, _), p in zip(df[need].iterrows(), preds):
        df.at[idx, "category"] = p["category"]
        conf[idx] = p["confidence"]
    existing = {(t.date, round(t.amount, 2), t.raw_description) for t in
                db.scalars(select(M.Transaction).where(M.Transaction.user_id == user.id))}
    n0 = db.query(M.Transaction).filter(M.Transaction.user_id == user.id).count()
    added, income_added, dupes, low_conf, by_cat = 0, 0, 0, [], {}
    for i, r in df.iterrows():
        d = r["date"].date()
        key = (d, round(float(r["amount"]), 2), r["raw_description"])
        if key in existing:
            dupes += 1
            continue
        existing.add(key)
        up = r["raw_description"].upper()
        if r["type"] == "credit" and any(h in up for h in INCOME_HINTS) and "REFUND" not in up:
            db.add(M.IncomeRecord(user_id=user.id, account_id=account_id, amount=float(r["amount"]),
                                  source="Salary" if "SALARY" in up else "Other income", date=d))
            income_added += 1
            continue
        db.add(M.Transaction(user_id=user.id, account_id=account_id if not card_id else None, card_id=card_id,
                             ref=f"{user.internal_id[-6:]}-U{n0 + added + 1:05d}", date=d, amount=float(r["amount"]), type=r["type"],
                             raw_description=r["raw_description"][:200], category=r["category"],
                             category_source="model" if conf[i] is not None else "given", merchant=None))
        added += 1
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        if conf[i] is not None and conf[i] < 0.5:
            low_conf.append({"description": r["raw_description"][:80], "predicted": r["category"], "confidence": conf[i]})
    db.commit()
    return {**report, "transactions_added": added, "income_records_added": income_added, "duplicates_skipped": dupes,
            "categorised_by_model": int(need.sum()), "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
            "low_confidence": low_conf[:20], "low_confidence_count": len(low_conf),
            "note": "Low-confidence categories can be corrected in Transaction Intelligence."}

"""Data-cleaning rules."""
from datetime import date

import pandas as pd

from app.services.cleaning import clean_transactions, standardise_category
from app.services.statement_import import parse_csv


def _tx(rows):
    return pd.DataFrame(rows, columns=["date", "amount", "type", "raw_description", "category", "account_id", "card_id"])


def test_duplicates_refunds_transfers():
    t, rep = clean_transactions(_tx([
        [date(2026, 5, 1), 1000, "debit", "AMAZON", "Shopping", 1, None],
        [date(2026, 5, 1), 1000, "debit", "AMAZON", "Shopping", 1, None],      # exact duplicate
        [date(2026, 5, 3), 400, "credit", "REFUND AMAZON", "Shopping", 1, None],  # refund
        [date(2026, 5, 4), 5000, "debit", "SELF TRANSFER", "Transfer", 1, None],  # not an expense
        [date(2026, 5, 5), 9000, "debit", "CC PAYMENT", "Card Payment", 1, None],  # not an expense
        [date(2026, 5, 6), 2000, "debit", "ATM WDL", "Cash", 1, None],
        [None, 50, "debit", "bad row", "Dining", 1, None],
    ]))
    assert rep["duplicates_removed"] == 1 and rep["dropped_missing_date_or_amount"] == 1 and rep["refunds"] == 1
    assert t["spend"].sum() == 1000 - 400 + 2000          # shopping net of refund + cash; transfers excluded


def test_category_synonyms():
    assert standardise_category("food") == "Dining" and standardise_category("Bills") == "Utilities"
    assert standardise_category(" grocery ") == "Groceries" and standardise_category(None) is None


def test_parse_csv_single_amount_layout():
    csv = b"Date,Narration,Amount,Type\n05/10/2026,UPI/DR/123456789012/SWIGGY/YESB/swiggy@ybl/Payment,450.00,DR\n06/10/2026,SALARY OCT,90000,CR\n,,,\n"
    df, rep = parse_csv(csv)
    assert len(df) == 2 and df.iloc[0]["type"] == "debit" and df.iloc[1]["type"] == "credit"
    assert df.iloc[0]["date"].day == 5 and df.iloc[0]["date"].month == 10   # day-first


def test_parse_csv_debit_credit_layout_with_header_junk():
    csv = (b"HDFC BANK Statement of account\nCustomer: TEST\n\nTxn Date,Particulars,Withdrawal,Deposit,Balance\n"
           b"2026-10-02,POS 4521XXXXXXXX1234 AMAZON BANGALORE,\"1,299.00\",,50000\n2026-10-03,NEFT CR SALARY,,\"85,000.00\",135000\n")
    df, rep = parse_csv(csv)
    assert rep["layout"] == "debit/credit columns" and list(df["amount"]) == [1299.0, 85000.0]
    assert list(df["type"]) == ["debit", "credit"]

"""Synthetic statement files with known ground truth, for testing the import pipeline.

These are NOT real bank statements. Layouts imitate the column headers of common Indian bank exports; narrations
come from app/data/narrations.py (the same synthetic templates the categoriser was trained on, including the formats
held out of its training). Every row carries its true class, so classification accuracy can be measured.
"""
from __future__ import annotations

import io
import random
from dataclasses import dataclass
from datetime import date, timedelta

from app.data import narrations as N

OWN_CARD_LAST4 = "4321"
OTHER_ACCOUNT_LAST4 = "7788"


@dataclass
class Row:
    date: date
    desc: str
    amount: float
    type: str              # debit | credit
    truth: str             # category, or "income:<source>"
    balance: float = 0.0


def _months(start: date, n: int):
    y, m = start.year, start.month
    for _ in range(n):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def bank_rows(start: date = date(2024, 11, 1), months: int = 24, seed: int = 3, opening: float = 150000.0,
              salary: float = 95000.0, raise_after: int = 12, raise_to: float = 105000.0, p2p_credits: bool = True) -> list[Row]:
    rng = random.Random(seed)
    rows: list[Row] = []
    for i, (y, m) in enumerate(_months(start, months)):
        d = lambda day: date(y, m, min(day, 28))  # noqa: E731
        sal = salary if i < raise_after else raise_to
        rows.append(Row(d(1), f"NEFT CR-HDFC0000123-ACME TECHNOLOGIES PVT LTD-{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][m-1]} PAYOUT", sal, "credit", "income:Salary"))
        rows.append(Row(d(3), f"NACH/DR/HDFC BANK EMI/{rng.randint(10**7, 10**8)}", 15000, "debit", "EMI"))
        rows.append(Row(d(5), f"IMPS/P2A/{rng.randint(10**11, 10**12)}/RENT FLAT", 25000, "debit", "Rent"))
        rows.append(Row(d(10), f"BSE STAR MF SIP {rng.randint(10**7, 10**8)}", 10000, "debit", "Investment"))
        rows.append(Row(d(7), f"UPI/DR/{rng.randint(10**11, 10**12)}/NETFLIX/YESB/netflix@ybl/Payment", 649, "debit", "Subscriptions"))
        rows.append(Row(d(12), f"BIL/BPAY/{rng.randint(10**8, 10**9)}/AIRTEL/AUTOPAY", 799, "debit", "Utilities"))
        rows.append(Row(d(15), f"CC PAYMENT HDFC BANK XX{OWN_CARD_LAST4}", round(rng.uniform(9000, 22000), 2), "debit", "Card Payment"))
        rows.append(Row(d(18), f"ATM WDL SBI ATM {rng.choice(N.CITIES)}", rng.choice([2000, 3000, 5000]), "debit", "Cash"))
        for _ in range(rng.randint(10, 16)):
            cat = rng.choice(["Dining", "Groceries", "Travel", "Shopping", "Health", "Fuel", "Entertainment"])
            desc, _, _ = N.merchant_narration(cat, rng)
            amt = {"Dining": (150, 1400), "Groceries": (300, 3500), "Travel": (80, 900), "Shopping": (400, 6000),
                   "Health": (200, 2500), "Fuel": (500, 3000), "Entertainment": (200, 1500)}[cat]
            rows.append(Row(d(rng.randint(1, 28)), desc, round(rng.uniform(*amt), 2), "debit", cat))
        if m in (3, 6, 9, 12):
            rows.append(Row(d(28), "SB INT PD 01-0" + str(m) + "-" + str(y), round(rng.uniform(300, 900), 2), "credit", "income:Interest"))
            rows.append(Row(d(20), f"NEFT DR-OWN ACCOUNT TRF-XX{OTHER_ACCOUNT_LAST4}", 20000, "debit", "Transfer"))
        if i % 5 == 2:
            src = next(r for r in reversed(rows) if r.truth == "Shopping")
            rows.append(Row(src.date + timedelta(days=4) if src.date.day < 24 else src.date, "REFUND " + src.desc[:60],
                            round(src.amount * 0.6, 2), "credit", "refund:Shopping"))
        if p2p_credits and i % 3 == 1:
            rows.append(Row(d(22), f"UPI/CR/{rng.randint(10**11, 10**12)}/RAHUL SHARMA/okaxis/dinner split", round(rng.uniform(300, 1800), 2),
                            "credit", "unrecognised"))
    rows.sort(key=lambda r: r.date)
    bal = opening
    for r in rows:
        bal += r.amount if r.type == "credit" else -r.amount
        r.balance = round(bal, 2)
    return rows


def card_rows(start: date = date(2024, 11, 1), months: int = 24, seed: int = 9) -> list[Row]:
    rng = random.Random(seed)
    rows: list[Row] = []
    for i, (y, m) in enumerate(_months(start, months)):
        for _ in range(rng.randint(6, 12)):
            cat = rng.choice(["Dining", "Shopping", "Travel", "Entertainment", "Groceries"])
            desc, _, _ = N.merchant_narration(cat, rng, fmt=rng.choice(N.CARD_FORMATS))
            rows.append(Row(date(y, m, rng.randint(1, 28)), desc, round(rng.uniform(250, 7000), 2), "debit", cat))
        rows.append(Row(date(y, m, 16), "PAYMENT RECEIVED - THANK YOU", round(rng.uniform(9000, 22000), 2), "credit", "Card Payment"))
        rows.append(Row(date(y, m, 2), f"SPOTIFY INDIA ONLINE MUMBAI IN", 119, "debit", "Subscriptions"))
        if i % 6 == 3:
            src = next(r for r in reversed(rows) if r.truth == "Shopping")
            rows.append(Row(src.date, src.desc + " REFUND", round(src.amount, 2), "credit", "refund:Shopping"))
    rows.sort(key=lambda r: r.date)
    return rows


# ---------------------------------------------------------------- writers (one per layout)
def _f(x: float) -> str:
    return f"{x:,.2f}"


def hdfc(rows: list[Row], junk: bool = True) -> bytes:
    out = io.StringIO()
    if junk:
        out.write("HDFC BANK Ltd.,,,,,,\nStatement of account,,,,,,\nAccount No : XXXXXXXX1234,,,,,,\n,,,,,,\n")
    out.write("Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n")
    for k, r in enumerate(rows):
        dd = r.date.strftime("%d/%m/%y")
        out.write(f'{dd},"{r.desc}",{1000000 + k:016d},{dd},"{_f(r.amount) if r.type == "debit" else ""}","{_f(r.amount) if r.type == "credit" else ""}","{_f(r.balance)}"\n')
    if junk:
        out.write(",,,,,,\nSTATEMENT SUMMARY :-,,,,,,\nOpening Balance,Dr Count,Cr Count,Debits,Credits,Closing Bal,\n")
    return out.getvalue().encode()


def sbi_newest_first(rows: list[Row]) -> bytes:
    out = io.StringIO()
    out.write("Account Name : TEST\nAddress : -\n\nTxn Date\tValue Date\tDescription\tRef No./Cheque No.\tDebit\tCredit\tBalance\n")
    for r in reversed(rows):
        dd = r.date.strftime("%d %b %Y")
        out.write(f"{dd}\t{dd}\t{r.desc}\t\t{_f(r.amount) if r.type == 'debit' else ' '}\t{_f(r.amount) if r.type == 'credit' else ' '}\t{_f(r.balance)}\n")
    out.write("**This is a computer generated statement**\n")
    return out.getvalue().encode()


def icici(rows: list[Row]) -> bytes:
    out = io.StringIO()
    out.write("S No.,Value Date,Transaction Date,Cheque Number,Transaction Remarks,Withdrawal Amount (INR ),Deposit Amount (INR ),Balance (INR )\n")
    for k, r in enumerate(rows, 1):
        dd = r.date.strftime("%d/%m/%Y")
        out.write(f'{k},{dd},{dd},-,"{r.desc}",{r.amount if r.type == "debit" else 0},{r.amount if r.type == "credit" else 0},{r.balance}\n')
    return out.getvalue().encode()


def kotak_semicolon(rows: list[Row]) -> bytes:
    out = io.StringIO()
    out.write("Sl. No.;Date;Description;Chq / Ref number;Amount;Dr / Cr;Balance;Dr / Cr\n")
    for k, r in enumerate(rows, 1):
        out.write(f"{k};{r.date.strftime('%d-%m-%Y')};{r.desc};;{_f(r.amount)};{'CR' if r.type == 'credit' else 'DR'};{_f(abs(r.balance))};{'CR' if r.balance >= 0 else 'DR'}\n")
    return out.getvalue().encode()


def generic_signed(rows: list[Row], with_balance: bool = True) -> bytes:
    out = io.StringIO()
    out.write("Date,Description,Amount" + (",Balance" if with_balance else "") + "\n")
    for r in rows:
        amt = -r.amount if r.type == "debit" else r.amount
        out.write(f'{r.date.isoformat()},"{r.desc}",{amt:.2f}' + (f",{r.balance:.2f}" if with_balance else "") + "\n")
    return out.getvalue().encode()


def card_statement(rows: list[Row]) -> bytes:
    out = io.StringIO()
    out.write("Credit Card Statement,,\nCard No: XXXX XXXX XXXX " + OWN_CARD_LAST4 + ",,\n,,\nDate,Transaction Details,Amount (in Rs.)\n")
    for r in rows:
        out.write(f'{r.date.strftime("%d/%m/%Y")},"{r.desc}","{_f(r.amount)}{" Cr" if r.type == "credit" else ""}"\n')
    return out.getvalue().encode()


def big_bank(n_rows: int = 150_000, seed: int = 21) -> tuple[bytes, float]:
    """A very large statement (HDFC-style, ~24 months). Returns (csv bytes, closing balance)."""
    rng = random.Random(seed)
    start = date(2024, 11, 1)
    span = 730
    days = sorted(rng.randrange(span) for _ in range(n_rows))
    out = io.StringIO()
    out.write("Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n")
    bal = 5_000_000.0
    cats = ["Dining", "Groceries", "Travel", "Shopping", "Health", "Fuel", "Entertainment", "Utilities", "Subscriptions"]
    for k, off in enumerate(days):
        dd = (start + timedelta(days=off)).strftime("%d/%m/%y")
        if k % 40 == 0:
            amt, typ, desc = round(rng.uniform(20000, 90000), 2), "credit", f"NEFT CR-HDFC0000123-CLIENT {rng.randint(1, 60)} PAYMENT"
        else:
            desc, _, _ = N.merchant_narration(rng.choice(cats), rng)
            amt, typ = round(rng.uniform(50, 2500), 2), "debit"
        bal += amt if typ == "credit" else -amt
        out.write(f'{dd},"{desc}",{k:016d},{dd},{_f(amt) if typ == "debit" else ""},{_f(amt) if typ == "credit" else ""},"{_f(bal)}"\n')
    return out.getvalue().encode(), round(bal, 2)

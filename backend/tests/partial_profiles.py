"""Builders for partially-populated private profiles, used by the robustness tests.

Each builder inserts ONLY what a real user might have entered by hand - no transactions or history are invented.
"""
from __future__ import annotations

from datetime import date

from app import models as M


def _acct(db, uid, bal=150000.0, rate=3.0):
    a = M.BankAccount(user_id=uid, bank_name="HDFC Bank", account_type="savings", account_masked="XXXX1111", balance=bal,
                      interest_rate=rate, is_primary=True)
    db.add(a)
    db.flush()
    return a


def _card(db, uid, limit=200000.0, out=150000.0):
    db.add(M.CreditCard(user_id=uid, issuer="ICICI Bank", card_name="Coral", last4="4321", credit_limit=limit, outstanding=out,
                        min_due=out * 0.05, due_day=12, apr=42.0))


def _loan(db, uid):
    db.add(M.Loan(user_id=uid, loan_type="Personal Loan", lender="Bajaj Finance", principal=500000, balance=380000, emi=16000,
                  interest_rate=14.0, tenure_months=36, remaining_months=26))


def _income(db, uid, months=(8, 9, 10), amount=90000.0, acct=None):
    for m in months:
        db.add(M.IncomeRecord(user_id=uid, account_id=acct, amount=amount, source="Salary", date=date(2026, m, 1)))


def _tx(db, uid, months=(9, 10), acct=None):
    n = 0
    for m in months:
        for d, amt, desc, cat in [(3, 22000, "IMPS RENT FLAT", "Rent"), (8, 640, "UPI/DR/1/SWIGGY/YESB/swiggy@ybl", "Dining"),
                                  (14, 3200, "UPI/DR/1/BIGBASKET/ICIC/bigbasket@ybl", "Groceries"), (20, 799, "BIL/BPAY/AIRTEL", "Utilities")]:
            n += 1
            db.add(M.Transaction(user_id=uid, account_id=acct, ref=f"P{uid}-{n}", date=date(2026, m, d), amount=amt, type="debit",
                                 raw_description=desc, category=cat, category_source="user"))


def _investments(db, uid):
    db.add(M.StockHolding(user_id=uid, symbol="INFY", company="Infosys", sector="IT", quantity=40, avg_buy_price=1400,
                          current_price=1650, buy_date=date(2023, 5, 10)))
    db.add(M.MutualFundHolding(user_id=uid, scheme="UTI Nifty 50 Index Fund", fund_type="index", units=1200, avg_nav=120,
                               current_nav=158, start_date=date(2022, 1, 5)))
    db.add(M.SIP(user_id=uid, scheme="UTI Nifty 50 Index Fund", amount=10000, sip_day=5, start_date=date(2022, 1, 5)))


def _everything_else(db, uid):
    db.add(M.FixedDeposit(user_id=uid, bank="SBI", kind="FD", principal=200000, interest_rate=7.0, start_date=date(2025, 4, 1),
                          maturity_date=date(2027, 4, 1)))
    db.add(M.FixedDeposit(user_id=uid, bank="SBI", kind="RD", principal=60000, interest_rate=6.5, start_date=date(2026, 1, 1),
                          maturity_date=date(2027, 1, 1)))
    for kind, val, liq in [("gold", 120000, "semi_liquid"), ("ppf", 300000, "locked"), ("epf", 450000, "locked"),
                           ("nps", 150000, "locked"), ("bonds", 50000, "semi_liquid"), ("crypto", 20000, "liquid"), ("cash", 8000, "liquid")]:
        db.add(M.OtherAsset(user_id=uid, kind=kind, description=kind.upper(), value=val, liquidity=liq))
    p = M.Property(user_id=uid, kind="Apartment", city="Pune", purchase_value=5500000, purchase_date=date(2021, 3, 1),
                   current_value=7000000, monthly_rent=0, is_self_occupied=True)
    db.add(p)
    db.flush()
    db.add(M.Loan(user_id=uid, loan_type="Home Loan", lender="HDFC", principal=4000000, balance=3300000, emi=34000,
                  interest_rate=8.6, tenure_months=240, remaining_months=190, property_id=p.id))
    db.add(M.InsurancePolicy(user_id=uid, kind="health", insurer="Niva Bupa", cover=1000000, annual_premium=18000))
    db.add(M.InsurancePolicy(user_id=uid, kind="term", insurer="HDFC Life", cover=10000000, annual_premium=14000))
    db.add(M.Goal(user_id=uid, name="Car", target_amount=800000, target_date=date(2028, 6, 1), current_amount=150000))
    db.add(M.RecurringPayment(user_id=uid, name="Netflix", category="Entertainment", amount=649, frequency="monthly", day_of_month=7))


def empty(db, uid): pass
def bank_only(db, uid): _acct(db, uid)
def card_only(db, uid): _card(db, uid)
def loan_only(db, uid): _loan(db, uid)
def investments_only(db, uid): _investments(db, uid)
def income_only(db, uid): _income(db, uid)
def spending_only(db, uid): _tx(db, uid, acct=_acct(db, uid).id)
def one_month(db, uid):
    a = _acct(db, uid).id
    _income(db, uid, months=(10,), acct=a)
    _tx(db, uid, months=(10,), acct=a)


def full_manual(db, uid):
    a = _acct(db, uid).id
    _card(db, uid, out=40000)
    _loan(db, uid)
    _income(db, uid, months=(5, 6, 7, 8, 9, 10), acct=a)
    _tx(db, uid, months=(5, 6, 7, 8, 9, 10), acct=a)
    _investments(db, uid)
    _everything_else(db, uid)


BUILDERS = {f.__name__: f for f in [empty, bank_only, card_only, loan_only, investments_only, income_only, spending_only,
                                     one_month, full_manual]}

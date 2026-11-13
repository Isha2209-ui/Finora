"""Synthetic financial-identity generator.

Produces clearly-labelled SYNTHETIC data:
  * 4 hand-specified demo identities (one per demo PAN), and
  * a training population of ordinary users (default 240) for the
    transaction-based models (anomaly detection, cash-flow forecasting, peers).

Everything is deterministic for a given seed, so results are reproducible.
"""
from __future__ import annotations

import calendar
import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from . import narrations as N

MONTHS = [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 11)]
AS_OF = date(2026, 10, 31)

# Expense classification used everywhere in Finora
ESSENTIAL = {"Rent", "Utilities", "Groceries", "Health", "Education", "Insurance", "Fuel"}
DISCRETIONARY = {"Dining", "Shopping", "Travel", "Entertainment", "Subscriptions"}
NON_EXPENSE = {"Transfer", "Card Payment", "Investment"}  # money moved, not spent
VARIABLE = ["Groceries", "Dining", "Shopping", "Travel", "Fuel", "Entertainment", "Health", "Utilities", "Education"]


def emi_amount(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 12 / 100
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def loan_balance(principal: float, annual_rate: float, months: int, paid: int) -> float:
    r = annual_rate / 12 / 100
    if r == 0:
        return principal * (months - paid) / months
    return principal * ((1 + r) ** months - (1 + r) ** paid) / ((1 + r) ** months - 1)


def _day(rng, y, m, lo=1, hi=None):
    last = calendar.monthrange(y, m)[1]
    return date(y, m, rng.randint(lo, min(hi or last, last)))


@dataclass
class Spec:
    internal_id: str
    name: str
    age: int
    occupation: str
    employment_type: str
    city: str
    archetype: str
    retirement_age_target: int
    pan: str | None = None
    salary: float = 0.0                       # monthly take-home (salaried)
    freelance_mean: float = 0.0               # monthly mean (self-employed)
    freelance_cv: float = 0.0
    bonus_month: int | None = None
    bonus: float = 0.0
    rent_paid: float = 0.0
    accounts: list[dict] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)      # + behaviour: full | min | late
    budgets: dict[str, float] = field(default_factory=dict)  # monthly base spend per variable category
    disc_trend: float = 0.0                   # monthly growth of discretionary spend
    card_share: float = 0.5
    atm_per_month: tuple[int, int] = (0, 1)
    subscriptions: list[tuple[str, float]] = field(default_factory=list)
    stocks: list[dict] = field(default_factory=list)
    mfs: list[dict] = field(default_factory=list)
    sips: list[dict] = field(default_factory=list)
    fds: list[dict] = field(default_factory=list)
    properties: list[dict] = field(default_factory=list)
    other_assets: list[dict] = field(default_factory=list)
    loans: list[dict] = field(default_factory=list)
    insurance: list[dict] = field(default_factory=list)
    goals: list[dict] = field(default_factory=list)
    planted_anomalies: int = 0
    random_anomaly_rate: float = 0.0
    is_demo: bool = False


# ================================================================= simulation
def simulate(spec: Spec, seed: int) -> dict:
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    out = {k: [] for k in ["transactions", "income", "recurring", "card_statements", "savings", "monthly"]}
    accts = spec.accounts
    primary = next((a for a in accts if a.get("is_primary")), accts[0])
    tx_n = 0

    def add_tx(d, amount, category, desc, merchant=None, *, account=None, card=None, typ="debit", anomaly=False):
        nonlocal tx_n
        tx_n += 1
        out["transactions"].append(dict(
            ref=f"{spec.internal_id[-6:]}-T{tx_n:05d}", date=d, amount=round(float(amount), 2), type=typ,
            raw_description=desc, category=category, merchant=merchant, injected_anomaly_label=anomaly,
            account_key=None if account is None else account["key"], card_key=None if card is None else card["key"]))

    # ---- recurring definitions
    if spec.rent_paid:
        out["recurring"].append(dict(name="House rent", category="Rent", amount=spec.rent_paid, day_of_month=5))
    for name, amt in spec.subscriptions:
        out["recurring"].append(dict(name=name, category="Subscriptions", amount=amt, day_of_month=rng.randint(2, 20)))
    for ln in spec.loans:
        out["recurring"].append(dict(name=f"{ln['loan_type']} EMI ({ln['lender']})", category="EMI",
                                     amount=ln["emi"], day_of_month=ln.get("emi_day", 5)))
    for s in spec.sips:
        out["recurring"].append(dict(name=f"SIP - {s['scheme']}", category="Investment", amount=s["amount"],
                                     day_of_month=s["sip_day"]))

    card_delay = {c["key"]: 0 for c in spec.cards}
    prev_bill = {c["key"]: c.get("opening_balance", 0.0) for c in spec.cards}
    prev_min_due = {c["key"]: round(max(200.0, c.get("opening_balance", 0.0) * 0.05), 0) for c in spec.cards}
    missed_sip_months = {s["scheme"]: set(s.get("missed_months", [])) for s in spec.sips}

    for mi, (y, m) in enumerate(MONTHS):
        month_key = f"{y}-{m:02d}"
        month_start = len(out["transactions"])

        # ---------------- income
        if spec.employment_type == "salaried":
            out["income"].append(dict(amount=spec.salary, source="Salary", date=date(y, m, 1), account_key=primary["key"]))
            if spec.bonus_month == m and spec.bonus:
                out["income"].append(dict(amount=spec.bonus, source="Annual bonus", date=date(y, m, 28),
                                          account_key=primary["key"]))
        else:
            factor = float(np.clip(nrng.normal(1.0, spec.freelance_cv), 0.3, 2.4))
            total = round(spec.freelance_mean * factor, -2)
            parts = nrng.dirichlet(np.ones(rng.randint(1, 3))) * total
            for p in parts:
                out["income"].append(dict(amount=round(float(p), -1), source="Client payment",
                                          date=_day(rng, y, m), account_key=primary["key"]))
        for p in spec.properties:
            if p.get("monthly_rent"):
                out["income"].append(dict(amount=p["monthly_rent"], source="Rental income", date=date(y, m, 7),
                                          account_key=primary["key"]))

        # ---------------- fixed outflows
        if spec.rent_paid:
            add_tx(date(y, m, 5), spec.rent_paid, "Rent", N.special_narration("Rent", rng), "Landlord", account=primary)
        for ln in spec.loans:
            if mi >= 12 - ln.get("months_active_in_window", 12):
                add_tx(date(y, m, ln.get("emi_day", 5)), ln["emi"], "EMI",
                       N.special_narration("EMI", rng, lender=ln["lender"]), ln["lender"], account=primary)
        for s in spec.sips:
            active = s.get("status", "active") == "active" or mi < s.get("stopped_after_index", 12)
            if active and month_key not in missed_sip_months[s["scheme"]]:
                add_tx(date(y, m, s["sip_day"]), s["amount"], "Investment",
                       N.special_narration("Investment", rng, scheme=s["scheme"]), s["scheme"], account=primary)
        for name, amt in spec.subscriptions:
            ch = spec.cards[0] if spec.cards else None
            desc, merch, _ = N.merchant_narration("Subscriptions", rng, rng.choice(N.CARD_FORMATS) if ch else
                                                  N.BANK_UPI_FORMAT.get(primary["bank_name"], "gpay"))
            add_tx(_day(rng, y, m, 2, 20), amt, "Subscriptions", desc, name, card=ch, account=None if ch else primary)
        for ins in spec.insurance:
            if ins.get("paid_by_user", True) and ins.get("premium_month") == m:
                add_tx(date(y, m, 15), ins["annual_premium"], "Insurance",
                       N.special_narration("Insurance", rng, lender=ins["insurer"]), ins["insurer"], account=primary)

        # ---------------- variable spending
        trend = (1 + spec.disc_trend) ** mi
        festive = 1.35 if (y, m) in [(2025, 11), (2026, 10)] else 1.0
        for cat, base in spec.budgets.items():
            if base <= 0:
                continue
            avg_ticket = {"Groceries": 1300, "Dining": 520, "Shopping": 2100, "Travel": 420, "Fuel": 1800,
                          "Entertainment": 850, "Health": 1100, "Utilities": 1200, "Education": 2500}[cat]
            budget = base * (trend if cat in DISCRETIONARY else 1.0) * (festive if cat == "Shopping" else 1.0)
            budget *= float(np.clip(nrng.normal(1.0, 0.12), 0.7, 1.4))
            n = max(1, int(round(budget / avg_ticket)))
            amounts = nrng.dirichlet(np.ones(n) * 2.0) * budget
            for amt in amounts:
                amt = max(30.0, float(amt))
                use_card = spec.cards and cat in DISCRETIONARY | {"Fuel", "Health"} and rng.random() < spec.card_share
                if use_card:
                    card = rng.choices(spec.cards, weights=[c["credit_limit"] for c in spec.cards])[0]
                    desc, merch, _ = N.merchant_narration(cat, rng, rng.choice(N.CARD_FORMATS))
                    add_tx(_day(rng, y, m), amt, cat, desc, merch, card=card)
                else:
                    acct = rng.choice(accts)
                    fmt = N.BANK_UPI_FORMAT.get(acct["bank_name"], "gpay") if rng.random() < 0.75 else \
                        rng.choice(["gpay", "phonepe", "paytm_wallet", "billdesk"] if cat == "Utilities" else
                                   ["gpay", "phonepe", "paytm_wallet"])
                    desc, merch, _ = N.merchant_narration(cat, rng, fmt)
                    add_tx(_day(rng, y, m), amt, cat, desc, merch, account=acct)

        # occasional big legitimate purchases (flight, electronics) - makes anomaly detection non-trivial
        if rng.random() < 0.10:
            cat = rng.choice(["Travel", "Shopping"])
            desc, merch, _ = N.merchant_narration(cat, rng, "card_online" if spec.cards else "gpay")
            add_tx(_day(rng, y, m), rng.uniform(6000, 14000) * (spec.budgets.get("Shopping", 4000) / 4000) ** 0.5,
                   cat, desc, merch, card=spec.cards[0] if spec.cards else None,
                   account=None if spec.cards else primary)

        # ATM withdrawals
        for _ in range(rng.randint(*spec.atm_per_month)):
            acct = rng.choice(accts)
            add_tx(_day(rng, y, m), round(rng.uniform(2000, 8000), -2), "Cash",
                   N.special_narration("Cash", rng, bank=acct["bank_name"], city=spec.city), "ATM", account=acct)

        # refunds
        shop = [t for t in out["transactions"][month_start:] if t["category"] == "Shopping" and t["type"] == "debit"]
        if shop and rng.random() < 0.18:
            src = rng.choice(shop)
            add_tx(src["date"] + timedelta(days=rng.randint(2, 9)) if src["date"].day < 20 else src["date"],
                   src["amount"] * rng.uniform(0.4, 1.0), "Shopping", "REFUND " + src["raw_description"][:60],
                   src["merchant"], account=None if src["card_key"] else primary,
                   card=next((c for c in spec.cards if c["key"] == src["card_key"]), None), typ="credit")

        # own-account transfers
        if len(accts) > 1 and rng.random() < 0.35:
            other = rng.choice([a for a in accts if a is not primary])
            add_tx(_day(rng, y, m, 20), round(rng.uniform(5000, 30000), -3), "Transfer",
                   N.special_narration("Transfer", rng, bank=other["bank_name"]), "Self", account=primary)

        # ---------------- planted anomalies (labelled; evaluation only)
        candidates = [t for t in out["transactions"][month_start:]
                      if t["category"] in {"Shopping", "Dining", "Entertainment", "Travel"} and t["type"] == "debit"
                      and not t["injected_anomaly_label"]]
        for t in candidates:
            if rng.random() < spec.random_anomaly_rate:
                t["amount"] = round(t["amount"] * rng.uniform(6, 14), 2)
                t["injected_anomaly_label"] = True

        # ---------------- credit-card: pay LAST month's bill, then generate THIS month's statement
        for c in spec.cards:
            k = c["key"]
            prev, prev_min = prev_bill[k], prev_min_due[k]
            if prev <= 0:
                paid, status = 0.0, -2                      # UCI: -2 = no consumption
            elif c["behaviour"] == "full":
                paid, status = prev, -1                     # UCI: -1 = paid in full
            elif month_key in c.get("late_months", []):
                paid = round(prev_min * rng.uniform(0.0, 0.6), 0)
                card_delay[k] += 1
                status = card_delay[k]                      # UCI: n = payment delayed n months
            else:
                frac = c.get("pay_fraction", 0.15)
                paid = round(min(prev, max(prev_min, prev * rng.uniform(frac * 0.7, frac * 1.3))), 0)
                card_delay[k] = 0
                status = 0                                  # UCI: 0 = revolving credit (min or more paid)
            if paid > 0:
                add_tx(date(y, m, min(c["due_day"], 28)), paid, "Card Payment",
                       N.special_narration("Card Payment", rng, card=c["issuer"]), c["issuer"], account=primary)
            carry = max(0.0, prev - paid)
            spends = sum(t["amount"] if t["type"] == "debit" else -t["amount"]
                         for t in out["transactions"][month_start:] if t["card_key"] == k)
            bill = max(0.0, carry * (1 + c["apr"] / 12 / 100) + spends)
            min_due = round(max(200.0, bill * 0.05), 0) if bill > 0 else 0.0
            out["card_statements"].append(dict(card_key=k, month=month_key, bill_amount=round(bill, 2),
                                               paid_amount=round(paid, 2), min_due=min_due, payment_status=status))
            prev_bill[k], prev_min_due[k] = bill, min_due
            c["_final_outstanding"], c["_last_min_due"] = round(bill, 2), min_due

        # ---------------- monthly summary
        month_tx = out["transactions"][month_start:]
        expenses = sum((-t["amount"] if t["type"] == "credit" else t["amount"])
                       for t in month_tx if t["category"] not in NON_EXPENSE)
        income = sum(i["amount"] for i in out["income"] if i["date"].year == y and i["date"].month == m)
        out["monthly"].append(dict(month=month_key, income=round(income, 2), expenses=round(expenses, 2),
                                   savings=round(income - expenses, 2)))
        if income - expenses > 0:
            out["savings"].append(dict(amount=round(income - expenses, -1), date=date(y, m, 28),
                                       note="Net monthly surplus"))

    # planted anomalies for demo profiles (fixed count, clearly unusual)
    if spec.planted_anomalies:
        pool = [t for t in out["transactions"] if t["category"] in {"Shopping", "Dining", "Entertainment"}
                and t["type"] == "debit" and not t["injected_anomaly_label"] and t["date"] >= date(2026, 5, 1)]
        for t in rng.sample(pool, k=min(spec.planted_anomalies, len(pool))):
            t["amount"] = round(t["amount"] * rng.uniform(9, 16), 2)
            t["injected_anomaly_label"] = True
        _recompute_monthly(out)
    return out


def _recompute_monthly(out):
    by = {}
    for t in out["transactions"]:
        if t["category"] in NON_EXPENSE:
            continue
        k = f"{t['date'].year}-{t['date'].month:02d}"
        by[k] = by.get(k, 0) + (-t["amount"] if t["type"] == "credit" else t["amount"])
    for r in out["monthly"]:
        r["expenses"] = round(by.get(r["month"], 0.0), 2)
        r["savings"] = round(r["income"] - r["expenses"], 2)


# ================================================================= demo identities
def _acct(key, bank, typ, bal, rate, primary=False):
    return dict(key=key, bank_name=bank, account_type=typ, account_masked=f"XXXX{random.Random(key).randint(1000, 9999)}",
                balance=bal, interest_rate=rate, is_primary=primary)


def _card(key, issuer, name, limit, apr, behaviour, **kw):
    return dict(key=key, issuer=issuer, card_name=name, last4=f"{random.Random(key).randint(1000, 9999)}",
                credit_limit=limit, apr=apr, behaviour=behaviour, due_day=kw.pop("due_day", 18), **kw)


def _loan(loan_type, lender, principal, rate, tenure, paid_months, **kw):
    emi = round(emi_amount(principal, rate, tenure), 0)
    bal = round(loan_balance(principal, rate, tenure, paid_months), 0)
    return dict(loan_type=loan_type, lender=lender, principal=principal, balance=bal, emi=emi, interest_rate=rate,
                tenure_months=tenure, remaining_months=tenure - paid_months, **kw)


def demo_specs() -> list[Spec]:
    """The four demo identities. Fictional PAN-like identifiers; synthetic data."""
    s1 = Spec(
        internal_id="FINORA_USER_001", pan="ABCDE1234F", name="Aarav Mehta", age=29, occupation="Software Engineer",
        employment_type="salaried", city="Jaipur", archetype="balanced", retirement_age_target=50,
        salary=120000, bonus_month=3, bonus=150000, rent_paid=24000,
        accounts=[_acct("a1", "HDFC Bank", "salary", 186400, 3.0, True), _acct("a2", "State Bank of India", "savings", 242000, 2.7)],
        cards=[_card("c1", "HDFC Bank", "Millennia", 200000, 42.0, "full")],
        budgets=dict(Groceries=7500, Dining=5500, Shopping=6000, Travel=3500, Fuel=2500, Entertainment=2000,
                     Health=1500, Utilities=4200, Education=1200),
        card_share=0.6, atm_per_month=(0, 1),
        subscriptions=[("Netflix", 649), ("Spotify", 119), ("Cult.fit", 1499)],
        stocks=[dict(symbol="TCS", company="Tata Consultancy Services", sector="IT", quantity=25, avg_buy_price=3380, current_price=3920, buy_date=date(2023, 4, 12)),
                dict(symbol="HDFCBANK", company="HDFC Bank", sector="Banking", quantity=60, avg_buy_price=1520, current_price=1745, buy_date=date(2023, 8, 3)),
                dict(symbol="RELIANCE", company="Reliance Industries", sector="Energy", quantity=40, avg_buy_price=1240, current_price=1420, buy_date=date(2024, 1, 18)),
                dict(symbol="ITC", company="ITC", sector="FMCG", quantity=150, avg_buy_price=410, current_price=455, buy_date=date(2023, 11, 9)),
                dict(symbol="LT", company="Larsen & Toubro", sector="Infrastructure", quantity=18, avg_buy_price=3150, current_price=3710, buy_date=date(2024, 6, 21)),
                dict(symbol="SUNPHARMA", company="Sun Pharmaceutical", sector="Pharma", quantity=30, avg_buy_price=1480, current_price=1690, buy_date=date(2024, 9, 2))],
        mfs=[dict(scheme="Parag Parikh Flexi Cap Fund - Direct Growth", fund_type="equity", units=4150, avg_nav=72.4, current_nav=91.2, start_date=date(2022, 7, 5)),
             dict(scheme="UTI Nifty 50 Index Fund - Direct Growth", fund_type="index", units=1720, avg_nav=148.0, current_nav=176.5, start_date=date(2022, 9, 5)),
             dict(scheme="HDFC Short Term Debt Fund - Direct Growth", fund_type="debt", units=4600, avg_nav=29.1, current_nav=32.4, start_date=date(2023, 2, 1))],
        sips=[dict(scheme="Parag Parikh Flexi Cap Fund", amount=15000, sip_day=7, start_date=date(2022, 7, 7)),
              dict(scheme="UTI Nifty 50 Index Fund", amount=10000, sip_day=7, start_date=date(2022, 9, 7)),
              dict(scheme="HDFC Short Term Debt Fund", amount=5000, sip_day=10, start_date=date(2023, 2, 10))],
        fds=[dict(bank="State Bank of India", kind="FD", principal=300000, interest_rate=7.1, start_date=date(2025, 6, 15), maturity_date=date(2027, 6, 15))],
        other_assets=[dict(kind="ppf", description="PPF - SBI", value=320000, liquidity="locked"),
                      dict(kind="epf", description="EPF (employer)", value=480000, liquidity="locked"),
                      dict(kind="gold", description="Sovereign Gold Bonds 2023-24", value=152000, liquidity="semi_liquid"),
                      dict(kind="cash", description="Cash in hand", value=15000, liquidity="liquid")],
        insurance=[dict(kind="term", insurer="HDFC Life", cover=15000000, annual_premium=14800, premium_month=4),
                   dict(kind="health", insurer="Niva Bupa", cover=1000000, annual_premium=12600, premium_month=8)],
        goals=[dict(name="Car purchase", target_amount=800000, target_date=date(2027, 12, 31), current_amount=240000),
               dict(name="House down payment", target_amount=2500000, target_date=date(2030, 12, 31), current_amount=300000)],
        planted_anomalies=1, is_demo=True)

    s2 = Spec(
        internal_id="FINORA_USER_002", pan="PQRST5678K", name="Riya Kapoor", age=27, occupation="Marketing Executive",
        employment_type="salaried", city="Mumbai", archetype="spender", retirement_age_target=55,
        salary=95000, rent_paid=32000,
        accounts=[_acct("a1", "ICICI Bank", "salary", 21800, 3.0, True), _acct("a2", "Kotak Mahindra Bank", "savings", 9400, 3.5)],
        cards=[_card("c1", "ICICI Bank", "Amazon Pay", 120000, 43.2, "min", pay_fraction=0.18, opening_balance=60000),
               _card("c2", "HDFC Bank", "Regalia", 150000, 42.0, "min", pay_fraction=0.16, opening_balance=85000),
               _card("c3", "SBI Card", "SimplyCLICK", 60000, 42.0, "min", pay_fraction=0.2, opening_balance=35000,
                     late_months=["2026-09", "2026-10"])],
        budgets=dict(Groceries=6000, Dining=9000, Shopping=11000, Travel=5000, Fuel=0, Entertainment=4500,
                     Health=1200, Utilities=3600, Education=0),
        disc_trend=0.03, card_share=0.85, atm_per_month=(1, 2),
        subscriptions=[("Netflix", 649), ("Spotify", 119), ("Amazon Prime", 299), ("YouTube Premium", 129), ("Disney+ Hotstar", 299)],
        stocks=[dict(symbol="ZOMATO", company="Eternal (Zomato)", sector="Consumer Tech", quantity=180, avg_buy_price=265, current_price=238, buy_date=date(2024, 11, 4)),
                dict(symbol="PAYTM", company="One97 Communications (Paytm)", sector="Consumer Tech", quantity=40, avg_buy_price=880, current_price=745, buy_date=date(2025, 1, 20)),
                dict(symbol="NYKAA", company="FSN E-Commerce (Nykaa)", sector="Consumer Tech", quantity=150, avg_buy_price=205, current_price=192, buy_date=date(2025, 2, 11)),
                dict(symbol="SWIGGY", company="Swiggy", sector="Consumer Tech", quantity=60, avg_buy_price=455, current_price=372, buy_date=date(2025, 3, 3)),
                dict(symbol="IRFC", company="Indian Railway Finance Corp", sector="Finance", quantity=120, avg_buy_price=168, current_price=131, buy_date=date(2024, 7, 15))],
        mfs=[dict(scheme="Axis ELSS Tax Saver Fund - Direct Growth", fund_type="elss", units=420, avg_nav=92.0, current_nav=101.5, start_date=date(2024, 1, 5))],
        sips=[dict(scheme="Axis ELSS Tax Saver Fund", amount=5000, sip_day=5, start_date=date(2024, 1, 5), status="stopped",
                   stopped_after_index=8, missed_months=["2026-02", "2026-03"])],
        other_assets=[dict(kind="epf", description="EPF (employer)", value=190000, liquidity="locked"),
                      dict(kind="cash", description="Cash in hand", value=4000, liquidity="liquid")],
        loans=[_loan("Personal Loan", "Bajaj Finance", 300000, 14.5, 36, 13),
               _loan("Consumer Durable Loan", "HDFC Bank", 80000, 0.0, 12, 5, months_active_in_window=5)],
        insurance=[dict(kind="health", insurer="Star Health (employer group)", cover=500000, annual_premium=0, paid_by_user=False)],
        goals=[dict(name="Europe trip", target_amount=350000, target_date=date(2027, 5, 31), current_amount=12000)],
        planted_anomalies=4, is_demo=True)

    home = _loan("Home Loan", "SBI Home Loans", 5800000, 8.75, 240, 54, property_key="p1")
    s3 = Spec(
        internal_id="FINORA_USER_003", pan="LMNOP2345D", name="Kabir Singh", age=38, occupation="Sales Manager",
        employment_type="salaried", city="Noida", archetype="loan_heavy", retirement_age_target=58,
        salary=165000, bonus_month=5, bonus=120000, rent_paid=0,
        accounts=[_acct("a1", "Axis Bank", "salary", 48200, 3.0, True), _acct("a2", "Punjab National Bank", "savings", 31500, 2.7)],
        cards=[_card("c1", "Axis Bank", "Flipkart", 250000, 43.0, "min", pay_fraction=0.45, opening_balance=25000)],
        budgets=dict(Groceries=11000, Dining=5500, Shopping=7000, Travel=3000, Fuel=6500, Entertainment=2500,
                     Health=3500, Utilities=6800, Education=9000),
        card_share=0.5, atm_per_month=(1, 2),
        subscriptions=[("Netflix", 649), ("JioCinema", 89)],
        stocks=[dict(symbol="SBIN", company="State Bank of India", sector="Banking", quantity=120, avg_buy_price=610, current_price=815, buy_date=date(2023, 3, 10)),
                dict(symbol="MARUTI", company="Maruti Suzuki", sector="Auto", quantity=8, avg_buy_price=10200, current_price=12600, buy_date=date(2023, 9, 1))],
        mfs=[dict(scheme="Mirae Asset Large Cap Fund - Direct Growth", fund_type="equity", units=2900, avg_nav=98.0, current_nav=121.0, start_date=date(2021, 4, 5))],
        sips=[dict(scheme="Mirae Asset Large Cap Fund", amount=5000, sip_day=10, start_date=date(2021, 4, 10), missed_months=["2026-07"])],
        fds=[dict(bank="Punjab National Bank", kind="FD", principal=100000, interest_rate=6.8, start_date=date(2026, 1, 10), maturity_date=date(2027, 1, 10))],
        properties=[dict(key="p1", kind="Apartment (3BHK)", city="Noida", purchase_value=7200000, purchase_date=date(2022, 4, 20), current_value=9600000, monthly_rent=0, is_self_occupied=True),
                    dict(key="p2", kind="Apartment (2BHK)", city="Gurugram", purchase_value=5500000, purchase_date=date(2019, 8, 1), current_value=7800000, monthly_rent=22000, is_self_occupied=False)],
        other_assets=[dict(kind="epf", description="EPF (employer)", value=950000, liquidity="locked"),
                      dict(kind="ppf", description="PPF - PNB", value=210000, liquidity="locked"),
                      dict(kind="gold", description="Gold jewellery", value=250000, liquidity="semi_liquid"),
                      dict(kind="cash", description="Cash in hand", value=20000, liquidity="liquid")],
        loans=[home, _loan("Car Loan", "HDFC Bank", 900000, 9.2, 60, 24), _loan("Personal Loan", "Axis Bank", 400000, 13.5, 36, 14)],
        insurance=[dict(kind="term", insurer="LIC", cover=7500000, annual_premium=18500, premium_month=2),
                   dict(kind="health", insurer="HDFC Ergo (family floater)", cover=500000, annual_premium=24800, premium_month=6)],
        goals=[dict(name="Child's higher education", target_amount=3000000, target_date=date(2036, 6, 30), current_amount=150000)],
        planted_anomalies=1, is_demo=True)

    s4 = Spec(
        internal_id="FINORA_USER_004", pan="XYZAB9876C", name="Neha Verma", age=31, occupation="Freelance Designer",
        employment_type="self_employed", city="Bengaluru", archetype="irregular", retirement_age_target=50,
        freelance_mean=115000, freelance_cv=0.45, rent_paid=26000,
        accounts=[_acct("a1", "HDFC Bank", "current", 145000, 0.0, True), _acct("a2", "Kotak Mahindra Bank", "savings", 62000, 3.5),
                  _acct("a3", "IDFC First Bank", "savings", 210000, 7.0)],
        cards=[_card("c1", "Kotak Mahindra Bank", "League Platinum", 100000, 42.0, "full")],
        budgets=dict(Groceries=7000, Dining=6500, Shopping=7000, Travel=5000, Fuel=1500, Entertainment=2500,
                     Health=1800, Utilities=4500, Education=2500),
        card_share=0.35, atm_per_month=(2, 4),
        subscriptions=[("Adobe Creative Cloud", 4230), ("Figma", 1300), ("Spotify", 119), ("Google One", 130)],
        stocks=[dict(symbol="INFY", company="Infosys", sector="IT", quantity=40, avg_buy_price=1450, current_price=1610, buy_date=date(2023, 5, 2)),
                dict(symbol="ASIANPAINT", company="Asian Paints", sector="Consumer", quantity=20, avg_buy_price=3050, current_price=2480, buy_date=date(2023, 10, 16)),
                dict(symbol="HINDUNILVR", company="Hindustan Unilever", sector="FMCG", quantity=25, avg_buy_price=2480, current_price=2390, buy_date=date(2024, 2, 7)),
                dict(symbol="BAJFINANCE", company="Bajaj Finance", sector="Finance", quantity=12, avg_buy_price=6900, current_price=8250, buy_date=date(2024, 3, 22)),
                dict(symbol="TITAN", company="Titan Company", sector="Consumer", quantity=15, avg_buy_price=3300, current_price=3560, buy_date=date(2024, 8, 9)),
                dict(symbol="DMART", company="Avenue Supermarts", sector="Retail", quantity=10, avg_buy_price=4100, current_price=4280, buy_date=date(2025, 1, 14))],
        mfs=[dict(scheme="Quant Small Cap Fund - Direct Growth", fund_type="equity", units=950, avg_nav=210.0, current_nav=246.0, start_date=date(2023, 1, 12)),
             dict(scheme="ICICI Prudential Equity & Debt Fund - Direct", fund_type="hybrid", units=5200, avg_nav=38.5, current_nav=43.1, start_date=date(2023, 6, 1))],
        sips=[dict(scheme="Quant Small Cap Fund", amount=10000, sip_day=12, start_date=date(2023, 1, 12),
                   missed_months=["2025-12", "2026-02", "2026-05", "2026-06", "2026-09"])],
        other_assets=[dict(kind="gold", description="Digital gold (SafeGold)", value=120000, liquidity="liquid"),
                      dict(kind="gold", description="Gold jewellery", value=280000, liquidity="semi_liquid"),
                      dict(kind="nps", description="NPS Tier-1", value=110000, liquidity="locked"),
                      dict(kind="cash", description="Cash in hand", value=85000, liquidity="liquid")],
        insurance=[],
        goals=[dict(name="Studio equipment", target_amount=400000, target_date=date(2027, 3, 31), current_amount=90000),
               dict(name="Emergency fund (6 months)", target_amount=600000, target_date=date(2027, 6, 30), current_amount=210000)],
        planted_anomalies=2, is_demo=True)
    return [s1, s2, s3, s4]


# ================================================================= training population
BANKS = ["HDFC Bank", "State Bank of India", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank", "IDFC First Bank",
         "Punjab National Bank"]
FIRST = ["Aarav", "Vivaan", "Aditi", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Rohan", "Saanvi", "Kabir",
         "Meera", "Reyansh", "Tara", "Vihaan", "Nisha", "Dev", "Pooja", "Siddharth", "Riya", "Harsh", "Simran"]
LAST = ["Sharma", "Verma", "Gupta", "Mehta", "Iyer", "Nair", "Reddy", "Singh", "Kapoor", "Joshi", "Malhotra",
        "Chopra", "Bose", "Das", "Patel", "Rao", "Kulkarni", "Sinha"]
CITIES = ["Jaipur", "Delhi", "Mumbai", "Bengaluru", "Pune", "Hyderabad", "Chandigarh", "Ahmedabad", "Noida", "Chennai"]


def population_spec(i: int, seed: int) -> Spec:
    rng = random.Random(seed)
    arche = ["balanced", "spender", "loan_heavy", "irregular"][i % 4]
    age = rng.randint(23, 52)
    salaried = arche != "irregular"
    income = round(rng.uniform(45000, 220000), -3)
    lifestyle = income / 100000
    disc = {"balanced": 0.8, "spender": 1.9, "loan_heavy": 0.85, "irregular": 1.1}[arche] * rng.uniform(0.8, 1.2)
    budgets = dict(Groceries=6500 * lifestyle ** 0.6, Dining=5000 * lifestyle * disc, Shopping=6000 * lifestyle * disc,
                   Travel=3500 * lifestyle * disc, Fuel=2500 * lifestyle ** 0.5 * rng.choice([0, 1, 1]),
                   Entertainment=1800 * lifestyle * disc, Health=1300 * lifestyle ** 0.5,
                   Utilities=3800 * lifestyle ** 0.5, Education=rng.choice([0, 0, 1500, 6000]) * lifestyle ** 0.5)
    n_acc = rng.randint(1, 3)
    banks = rng.sample(BANKS, n_acc)
    accounts = [_acct(f"a{k + 1}", b, "salary" if k == 0 and salaried else "savings",
                      round(income * rng.uniform(0.3, 3.0), -2), rng.choice([2.7, 3.0, 3.5]), k == 0)
                for k, b in enumerate(banks)]
    n_cards = rng.choice([0, 1, 1, 2, 3] if arche == "spender" else [0, 1, 1, 2])
    cards = []
    for k in range(n_cards):
        beh = "min" if (arche == "spender" and rng.random() < 0.7) or rng.random() < 0.15 else "full"
        cards.append(_card(f"c{k + 1}", rng.choice(BANKS), rng.choice(["Classic", "Platinum", "Rewards", "Cashback"]),
                           round(income * rng.uniform(0.8, 2.2), -4), 42.0, beh, pay_fraction=rng.uniform(0.12, 0.4),
                           opening_balance=round(income * rng.uniform(0.2, 0.9), -3) if beh == "min" else 0.0))
    loans = []
    if arche == "loan_heavy":
        loans.append(_loan("Home Loan", "SBI Home Loans", round(income * rng.uniform(30, 45), -4), 8.75, 240, rng.randint(12, 80)))
        loans.append(_loan("Car Loan", "HDFC Bank", round(income * rng.uniform(5, 8), -4), 9.2, 60, rng.randint(6, 40)))
        if rng.random() < 0.6:
            loans.append(_loan("Personal Loan", "Bajaj Finance", round(income * rng.uniform(2, 4), -4), 14.0, 36, rng.randint(3, 25)))
    elif rng.random() < 0.3:
        loans.append(_loan(rng.choice(["Personal Loan", "Car Loan", "Education Loan"]), "Axis Bank",
                           round(income * rng.uniform(2, 6), -4), 11.5, 48, rng.randint(3, 30)))
    sip_amt = round(income * {"balanced": 0.18, "spender": 0.03, "loan_heavy": 0.04, "irregular": 0.08}[arche]
                    * rng.uniform(0.5, 1.5), -3)
    sips = [dict(scheme="Nifty 50 Index Fund", amount=sip_amt, sip_day=7, start_date=date(2023, 1, 7))] if sip_amt >= 1000 else []
    spec = Spec(
        internal_id=f"POP_{i:04d}", name=f"{rng.choice(FIRST)} {rng.choice(LAST)}", age=age,
        occupation=rng.choice(["Engineer", "Analyst", "Manager", "Teacher", "Consultant", "Designer", "Executive"]),
        employment_type="salaried" if salaried else "self_employed", city=rng.choice(CITIES), archetype=arche,
        retirement_age_target=60, salary=income if salaried else 0, freelance_mean=0 if salaried else income,
        freelance_cv=0 if salaried else rng.uniform(0.3, 0.6), bonus_month=3 if salaried and rng.random() < 0.5 else None,
        bonus=round(income * rng.uniform(0.5, 1.2), -3), rent_paid=round(income * rng.uniform(0.12, 0.28), -2) if rng.random() < 0.75 else 0,
        accounts=accounts, cards=cards, budgets=budgets, disc_trend=0.025 if arche == "spender" else 0.0,
        card_share=rng.uniform(0.3, 0.85), atm_per_month=(0, 3), subscriptions=[("Netflix", 649)] if rng.random() < 0.6 else [],
        loans=loans, sips=sips, random_anomaly_rate=0.012)
    return spec


def population_specs(n: int = 240, seed: int = 42) -> list[Spec]:
    return [population_spec(i, seed * 100_000 + i) for i in range(n)]

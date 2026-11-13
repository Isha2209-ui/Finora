"""Create all tables and load the demo identities + training population.

Usage:  python -m app.data.seed            (drops and recreates everything)
"""
from __future__ import annotations

import time
from datetime import date

from sqlalchemy import insert

from .. import models as M
from ..database import Base, SessionLocal, engine
from ..services import pan as P
from . import generator as G

N_POPULATION = 240


def _insert_identity(db, spec: G.Spec, sim: dict) -> int:
    user = M.User(internal_id=spec.internal_id, name=spec.name, age=spec.age, occupation=spec.occupation,
                  employment_type=spec.employment_type, city=spec.city, archetype=spec.archetype,
                  retirement_age_target=spec.retirement_age_target, is_demo=spec.is_demo,
                  pan_hash=P.hash_pan(spec.pan) if spec.pan else None,
                  pan_masked=P.mask(spec.pan) if spec.pan else None)
    db.add(user)
    db.flush()
    uid = user.id

    acct_ids = {}
    for a in spec.accounts:
        row = M.BankAccount(user_id=uid, bank_name=a["bank_name"], account_type=a["account_type"],
                            account_masked=a["account_masked"], balance=a["balance"],
                            interest_rate=a["interest_rate"], is_primary=a.get("is_primary", False))
        db.add(row)
        db.flush()
        acct_ids[a["key"]] = row.id
    card_ids = {}
    for c in spec.cards:
        row = M.CreditCard(user_id=uid, issuer=c["issuer"], card_name=c["card_name"], last4=c["last4"],
                           credit_limit=c["credit_limit"], outstanding=c.get("_final_outstanding", 0.0),
                           min_due=c.get("_last_min_due", 0.0), due_day=c["due_day"], apr=c["apr"])
        db.add(row)
        db.flush()
        card_ids[c["key"]] = row.id
    prop_ids = {}
    for p in spec.properties:
        row = M.Property(user_id=uid, kind=p["kind"], city=p["city"], purchase_value=p["purchase_value"],
                         purchase_date=p["purchase_date"], current_value=p["current_value"],
                         monthly_rent=p.get("monthly_rent", 0.0), is_self_occupied=p.get("is_self_occupied", True))
        db.add(row)
        db.flush()
        prop_ids[p["key"]] = row.id

    rows = lambda model, items: db.execute(insert(model), items) if items else None  # noqa: E731
    rows(M.CardStatement, [dict(card_id=card_ids[s["card_key"]], month=s["month"], bill_amount=s["bill_amount"],
                                paid_amount=s["paid_amount"], min_due=s["min_due"], payment_status=s["payment_status"])
                           for s in sim["card_statements"]])
    rows(M.IncomeRecord, [dict(user_id=uid, account_id=acct_ids.get(i["account_key"]), amount=i["amount"],
                               source=i["source"], date=i["date"]) for i in sim["income"]])
    rows(M.Transaction, [dict(user_id=uid, account_id=acct_ids.get(t["account_key"]), card_id=card_ids.get(t["card_key"]),
                              ref=t["ref"], date=t["date"], amount=t["amount"], type=t["type"],
                              raw_description=t["raw_description"], category=t["category"], category_source="given",
                              merchant=t["merchant"], injected_anomaly_label=t["injected_anomaly_label"])
                         for t in sim["transactions"]])
    rows(M.RecurringPayment, [dict(user_id=uid, **r) for r in sim["recurring"]])
    rows(M.SavingsRecord, [dict(user_id=uid, **s) for s in sim["savings"]])
    rows(M.MonthlySummary, [dict(user_id=uid, **m) for m in sim["monthly"]])
    rows(M.StockHolding, [dict(user_id=uid, **s) for s in spec.stocks])
    rows(M.MutualFundHolding, [dict(user_id=uid, **f) for f in spec.mfs])
    rows(M.SIP, [dict(user_id=uid, scheme=s["scheme"], amount=s["amount"], sip_day=s["sip_day"],
                      start_date=s["start_date"], status=s.get("status", "active"),
                      missed_last_12m=len(s.get("missed_months", [])) + (12 - s.get("stopped_after_index", 12)))
                 for s in spec.sips])
    rows(M.FixedDeposit, [dict(user_id=uid, **f) for f in spec.fds])
    rows(M.OtherAsset, [dict(user_id=uid, **o) for o in spec.other_assets])
    rows(M.Loan, [dict(user_id=uid, loan_type=l["loan_type"], lender=l["lender"], principal=l["principal"],
                       balance=l["balance"], emi=l["emi"], interest_rate=l["interest_rate"],
                       tenure_months=l["tenure_months"], remaining_months=l["remaining_months"],
                       property_id=prop_ids.get(l.get("property_key"))) for l in spec.loans])
    rows(M.InsurancePolicy, [dict(user_id=uid, kind=i["kind"], insurer=i["insurer"], cover=i["cover"],
                                  annual_premium=i["annual_premium"]) for i in spec.insurance])
    rows(M.Goal, [dict(user_id=uid, **g) for g in spec.goals])
    return uid


def build_net_worth_history(db, uid: int):
    """Monthly net-worth snapshots, reconstructed backwards from today's position."""
    from ..services.loader import load_identity
    from ..services.calculations import net_worth

    ident = load_identity(db, uid)
    nw = net_worth(ident)
    monthly = sorted(ident.monthly, key=lambda r: r["month"])
    net, liabs = nw["net_worth"], nw["total_liabilities"]
    market_assets = nw["breakdown"].get("Equity", 0) + nw["breakdown"].get("Mutual funds", 0)
    principal_paid = sum(l["emi"] * 0.45 for l in ident.loans)  # approx. principal share of EMIs
    snaps = []
    for idx in range(len(monthly) - 1, -1, -1):
        snaps.append(dict(user_id=uid, month=monthly[idx]["month"], assets=round(net + liabs, 0), liabilities=round(liabs, 0),
                          net_worth=round(net, 0)))
        # Step back one month: net worth changed by that month's savings plus ~0.9% market growth;
        # liabilities fell by loan principal repaid and rose by any deficit funded on credit.
        s = monthly[idx]["savings"]
        net -= s + market_assets * 0.009
        liabs = max(0.0, liabs + principal_paid - max(0.0, -s))
    db.execute(insert(M.NetWorthSnapshot), list(reversed(snaps)))


def run(n_population: int = N_POPULATION, verbose: bool = True):
    t0 = time.time()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        for k, spec in enumerate(G.demo_specs()):
            sim = G.simulate(spec, 7000 + k)
            uid = _insert_identity(db, spec, sim)
            db.flush()
            build_net_worth_history(db, uid)
        for i, spec in enumerate(G.population_specs(n_population)):
            uid = _insert_identity(db, spec, G.simulate(spec, 1000 + i))
            db.flush()
            build_net_worth_history(db, uid)
        db.commit()
    finally:
        db.close()
    if verbose:
        print(f"Seeded 4 demo identities + {n_population} population users in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    run()

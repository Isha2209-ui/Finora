"""One call that computes a person's whole deterministic financial picture."""
from __future__ import annotations

from . import calculations as C
from . import fire as F
from . import tax as T
from .cleaning import detect_recurring
from .loader import Identity

METROS = {"Mumbai", "Delhi", "Kolkata", "Chennai"}


def investable_corpus(ident: Identity) -> float:
    """Assets that can fund retirement: everything financial except the operating bank buffer.
    The self-occupied home is excluded (you live in it); rented-out property is included."""
    nw = C.net_worth(ident)["breakdown"]
    fin = sum(v for k, v in nw.items() if k not in {"Real estate", "Bank balances", "Cash in hand"})
    rental_property = sum(p["current_value"] for p in ident.properties if not p["is_self_occupied"])
    return fin + rental_property


def _fire_unavailable(ident: Identity, corpus: float, monthly_invest: float, reason: str) -> dict:
    """FIRE needs annual expenses. Without measured spending we do not guess them: the projection is withheld, but the
    inputs we DO know are returned so the planner can run with expenses the user types in."""
    d = F.DEFAULTS
    none = ["fire_number", "lean_fire_number", "fat_fire_number", "fire_age", "lean_fire_age", "fat_fire_age", "years_to_fire",
            "progress_pct", "coast_fire_number", "coast_fire_reached", "corpus_at_target_age", "shortfall_at_target_age",
            "monthly_investment_needed_for_target", "on_track", "success_probability_pct"]
    return {"available": False, "reason": reason, **{k: None for k in none}, "monte_carlo": {}, "projection": [],
            "retirement_age_target": ident.user["retirement_age_target"], "note": reason,
            "inputs": {"current_corpus": round(corpus), "monthly_investment": round(monthly_invest), "age": ident.user["age"],
                       "annual_expenses": None, "nominal_return_pct": round(d["nominal_return"] * 100, 2),
                       "inflation_pct": round(d["inflation"] * 100, 2), "withdrawal_rate_pct": round(d["swr"] * 100, 2),
                       "annual_step_up_pct": round(d["step_up"] * 100, 2),
                       "retirement_age_target": ident.user["retirement_age_target"]}}


def completeness(ident: Identity, cf: dict) -> dict:
    """What Finora knows about this person, what it does not, and which results each gap holds back."""
    checks = [
        ("Personal details", True, None, []),
        ("Bank accounts", bool(ident.accounts), "Add your bank accounts and balances.", ["Net worth", "Emergency fund", "Runway"]),
        ("Income", cf["income_known"], "Add income records (salary, client payments) or upload a statement with credits.",
         ["Savings rate", "Debt load", "Investing pillar", "Tax estimate", "Insurance needs", "Decision Simulator"]),
        ("Spending history", cf["spending_known"], "Add transactions or upload a bank/card statement CSV.",
         ["Savings rate", "Emergency-fund months", "FIRE projection", "Forecast", "Anomaly check", "Budget", "Decision Simulator"]),
        ("Three months of history", cf["coverage"]["months"] >= 3 and cf["spending_known"],
         "At least 3 months of transactions make averages, forecasts and peer comparison meaningful.",
         ["Cash-flow forecast", "Peer comparison"]),
        ("Credit cards", bool(ident.cards), "Add credit cards if you have any (skip if you have none).", []),
        ("Loans", bool(ident.loans), "Add loans if you have any (skip if you have none).", []),
        ("Insurance", bool(ident.insurance), "Add term and health policies, or skip if you have none.", ["Protection pillar"]),
        ("Investments", bool(ident.stocks or ident.mfs or ident.sips or ident.fds or ident.other_assets),
         "Add stocks, funds, SIPs, deposits, EPF/PPF/NPS, gold or other assets.", ["Net worth", "FIRE corpus", "Allocation"]),
        ("Goals", bool(ident.goals), "Add goals such as a car, a home or education.", ["Goal planning"]),
    ]
    items = [{"item": n, "present": bool(p), "hint": None if p else h, "affects": [] if p else a} for n, p, h, a in checks]
    score = round(sum(i["present"] for i in items) / len(items) * 100)
    return {"score_pct": score, "items": items, "missing": [i["item"] for i in items if not i["present"]],
            "note": "Completeness shows what Finora knows. Items you do not have (e.g. no loans) can be left empty; "
                    "nothing is filled in for you."}


def build(ident: Identity, fire_overrides: dict | None = None) -> dict:
    f, t, _ = C.monthly_frame(ident)
    cf = C.cash_flow(ident)
    inc_known, spend_known = cf["income_known"], cf["spending_known"]
    avg_inc, avg_exp = cf["avg_monthly_income"], cf["avg_monthly_expenses"]
    essential_monthly = float(f["essential"].mean() + f["emi"].mean()) if spend_known else None
    nw = C.net_worth(ident)
    liq = C.liquidity(ident, avg_exp, essential_monthly)
    cred = C.credit_analysis(ident)
    debt = C.debt_analysis(ident, avg_inc)
    ins = C.insurance_analysis(ident, avg_inc)
    inv = C.investment_analysis(ident, avg_inc)
    sip_monthly = float(sum(s["amount"] for s in ident.sips if s["status"] == "active"))
    # measured from transactions when there are any; otherwise the active SIPs the user entered (a stated commitment)
    # Measured from Investment transactions when the history contains any; otherwise the active SIPs the user entered
    # (a stated commitment). Demo identities always have investment transactions, so they use the measured figure.
    has_invest_tx = spend_known and float(f["invested"].sum()) > 0
    monthly_invest = float(f["invested"].tail(6).mean()) if has_invest_tx else sip_monthly
    non_liability_debt = sum(l["balance"] for l in ident.loans if l.get("property_id") is None) + \
        sum(c["outstanding"] for c in ident.cards)
    corpus = max(0.0, investable_corpus(ident) - non_liability_debt)
    if not spend_known:
        fire = _fire_unavailable(ident, corpus, monthly_invest, "Needs spending history to know your yearly expenses. "
                                 "Add transactions or upload a statement, or enter expected yearly expenses in the FIRE planner.")
    else:
        # Retirement spending: today's expenses minus EMIs (loans end) - a standard planning assumption
        retire_exp = max(1.0, (avg_exp - float(f["emi"].mean())) * 12)
        fire = F.project(corpus, monthly_invest, ident.user["age"], retire_exp,
                         retirement_age_target=ident.user["retirement_age_target"], **(fire_overrides or {}))
        fire["available"] = True
        if inc_known:
            surplus_invest = max(monthly_invest, cf["avg_monthly_savings"] * 0.8)
            alt = F.project(corpus, surplus_invest, ident.user["age"], retire_exp,
                            retirement_age_target=ident.user["retirement_age_target"], **(fire_overrides or {}))
            fire["if_you_invested_80pct_of_surplus"] = {"monthly_investment": round(surplus_invest), "fire_age": alt["fire_age"],
                                                       "success_probability_pct": alt["success_probability_pct"]}
    fire["corpus_definition"] = ("Investments + FDs + gold + EPF/PPF/NPS + rented-out property, minus card dues and "
                                 "unsecured loans. Self-occupied home and day-to-day bank balance are excluded.")
    fire["expense_definition"] = "Average monthly expenses over the period, excluding EMIs (assumed repaid by retirement)."
    salaried = ident.user["employment_type"] == "salaried"
    # demo: take-home treated as gross taxable income, annualised from the measured months
    gross = float(avg_inc * 12) if inc_known else 0.0
    home_interest = sum(l["balance"] * l["interest_rate"] / 100 for l in ident.loans if l["loan_type"] == "Home Loan")
    elss = sum(s["amount"] * 12 for s in ident.sips if "ELSS" in s["scheme"] and s["status"] == "active")
    ppf_like = 150000 if any(o["kind"] in {"ppf", "epf"} for o in ident.other_assets) else 0
    if inc_known:
        tax = T.compare(gross, salaried, sec_80c=min(150000, elss + ppf_like * 0.5),
                        sec_80d=sum(p["annual_premium"] for p in ident.insurance if p["kind"] == "health"),
                        home_loan_interest=home_interest)
        tax["available"] = True
        tax["note"] = ("Estimate: average recorded monthly income x 12 is treated as gross taxable income; deductions are "
                       "inferred from the profile.")
    else:
        tax = {"available": False, "note": "Needs income records to estimate tax. The tax comparison tool works with any income you type."}
    return {
        "profile": {k: ident.user[k] for k in ["internal_id", "pan_masked", "name", "age", "occupation", "employment_type",
                                                 "city", "retirement_age_target", "is_demo"]},
        "cash_flow": cf, "net_worth": nw, "allocation": C.asset_allocation(ident), "liquidity": liq,
        "credit": cred, "debt": debt, "insurance": ins, "investments": inv,
        "commitments": C.commitments(ident, liq["emergency_pool"]),
        "idle_money": C.idle_money(ident, avg_exp), "budget": C.budget_scenarios(ident, f, t, inc_known),
        "goals": C.goals_progress(ident), "recurring_detected": detect_recurring(t)[:15],
        "health_score": C.health_score(cf, liq, cred, debt, ins, inv),
        "fire": fire, "tax": tax,
        "data_notice": ("Synthetic demonstration data. " if ident.user.get("kind") in ("template", "sandbox") else
                        "Data you entered or uploaded. ") + "Market prices are stored values as of " + inv["prices_as_of"] + ".",
        "completeness": completeness(ident, cf),
    }

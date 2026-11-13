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


def build(ident: Identity, fire_overrides: dict | None = None) -> dict:
    f, t, _ = C.monthly_frame(ident)
    cf = C.cash_flow(ident)
    avg_inc, avg_exp = cf["avg_monthly_income"], cf["avg_monthly_expenses"]
    essential_monthly = float(f["essential"].mean() + f["emi"].mean())
    nw = C.net_worth(ident)
    liq = C.liquidity(ident, avg_exp, essential_monthly)
    cred = C.credit_analysis(ident)
    debt = C.debt_analysis(ident, avg_inc)
    ins = C.insurance_analysis(ident, avg_inc)
    inv = C.investment_analysis(ident, avg_inc)
    monthly_invest = float(f["invested"].tail(6).mean())
    non_liability_debt = sum(l["balance"] for l in ident.loans if l.get("property_id") is None) + \
        sum(c["outstanding"] for c in ident.cards)
    corpus = max(0.0, investable_corpus(ident) - non_liability_debt)
    # Retirement spending: today's expenses minus EMIs (loans end) - a standard planning assumption
    retire_exp = max(1.0, (avg_exp - float(f["emi"].mean())) * 12)
    fire = F.project(corpus, monthly_invest, ident.user["age"], retire_exp,
                     retirement_age_target=ident.user["retirement_age_target"], **(fire_overrides or {}))
    surplus_invest = max(monthly_invest, cf["avg_monthly_savings"] * 0.8)
    alt = F.project(corpus, surplus_invest, ident.user["age"], retire_exp,
                    retirement_age_target=ident.user["retirement_age_target"], **(fire_overrides or {}))
    fire["if_you_invested_80pct_of_surplus"] = {"monthly_investment": round(surplus_invest), "fire_age": alt["fire_age"],
                                               "success_probability_pct": alt["success_probability_pct"]}
    fire["corpus_definition"] = ("Investments + FDs + gold + EPF/PPF/NPS + rented-out property, minus card dues and "
                                 "unsecured loans. Self-occupied home and day-to-day bank balance are excluded.")
    fire["expense_definition"] = "Average monthly expenses over the period, excluding EMIs (assumed repaid by retirement)."
    salaried = ident.user["employment_type"] == "salaried"
    gross = float(ident.income["amount"].sum())  # demo: take-home treated as gross taxable income
    home_interest = sum(l["balance"] * l["interest_rate"] / 100 for l in ident.loans if l["loan_type"] == "Home Loan")
    elss = sum(s["amount"] * 12 for s in ident.sips if "ELSS" in s["scheme"] and s["status"] == "active")
    ppf_like = 150000 if any(o["kind"] in {"ppf", "epf"} for o in ident.other_assets) else 0
    tax = T.compare(gross, salaried, sec_80c=min(150000, elss + ppf_like * 0.5),
                    sec_80d=sum(p["annual_premium"] for p in ident.insurance if p["kind"] == "health"),
                    home_loan_interest=home_interest)
    tax["note"] = "Demo estimate: recorded income is treated as gross taxable income; deductions are inferred from the profile."
    return {
        "profile": {k: ident.user[k] for k in ["internal_id", "pan_masked", "name", "age", "occupation", "employment_type",
                                                 "city", "retirement_age_target", "is_demo"]},
        "cash_flow": cf, "net_worth": nw, "allocation": C.asset_allocation(ident), "liquidity": liq,
        "credit": cred, "debt": debt, "insurance": ins, "investments": inv,
        "idle_money": C.idle_money(ident, avg_exp), "budget": C.budget_scenarios(ident, f, t),
        "goals": C.goals_progress(ident), "recurring_detected": detect_recurring(t)[:15],
        "health_score": C.health_score(cf, liq, cred, debt, ins, inv),
        "fire": fire, "tax": tax,
        "data_notice": "Synthetic demonstration data. Market prices are stored values as of " + inv["prices_as_of"] + ".",
    }

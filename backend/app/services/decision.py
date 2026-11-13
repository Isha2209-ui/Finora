"""Decision Simulator - "should I make this big purchase?"

Works for any purchase (car, home, bike, phone, trip, education, wedding ...).
Everything is computed from the person's own numbers; the verdict comes from
fixed, published thresholds (no AI involved in the verdict).

Verdict rules
  NOT ADVISABLE if any:  total EMIs > 50% of income | monthly surplus after purchase < 0
                         | runway after purchase < 1 month | down payment > liquid savings
  STRETCH       if any:  total EMIs > 40% of income | runway after < 3 months
                         | savings rate after < 10% | FIRE delayed by more than 3 years
                         | (vehicles) price > 50% of annual income
  AFFORDABLE    otherwise
"""
from __future__ import annotations

from . import fire as F
from .loader import Identity
from .snapshot import build

RUNNING_COST_DEFAULTS = {  # annual, as a share of price (insurance + maintenance etc.)
    "car": 0.06, "bike": 0.07, "home": 0.012, "phone": 0.0, "gadget": 0.0, "trip": 0.0, "education": 0.0,
    "wedding": 0.0, "other": 0.0,
}


def emi(principal: float, annual_rate: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    i = annual_rate / 12 / 100
    return principal / months if i == 0 else principal * i * (1 + i) ** months / ((1 + i) ** months - 1)


def _scenario(name: str, snap: dict, *, price: float, down: float, rate: float, months: int, running_monthly: float,
              wait_months: int = 0, item_type: str = "other") -> dict:
    cf, liq, debt, fire = snap["cash_flow"], snap["liquidity"], snap["debt"], snap["fire"]
    income, expenses = cf["avg_monthly_income"], cf["avg_monthly_expenses"]
    surplus = cf["avg_monthly_savings"]
    pool = liq["emergency_pool"] + max(0.0, surplus) * wait_months  # savings accumulated while waiting
    down = min(price, down + (max(0.0, surplus) * wait_months if wait_months else 0.0)) if wait_months else down
    loan = max(0.0, price - down)
    e = emi(loan, rate, months)
    total_interest = e * months - loan
    new_emi_total = debt["total_emi"] + e
    new_expenses = expenses + e + running_monthly
    new_surplus = income - new_expenses
    pool_after = pool - down
    runway_before = liq["runway_months"] or 0.0
    runway_after = pool_after / new_expenses if new_expenses else 0.0
    fi = fire["inputs"]
    # FIRE after: corpus loses the down payment that exceeds idle bank cash; monthly investing shrinks if surplus can't cover it
    bank_buffer = liq["immediate"]
    corpus_hit = max(0.0, down - bank_buffer)
    invest_after = max(0.0, min(fi["monthly_investment"], fi["monthly_investment"] + min(0.0, new_surplus - fi["monthly_investment"])))
    kw = dict(nominal_return=fi["nominal_return_pct"] / 100, inflation=fi["inflation_pct"] / 100,
              swr=fi["withdrawal_rate_pct"] / 100, step_up=fi["annual_step_up_pct"] / 100)
    f_after = F.project(max(0.0, fi["current_corpus"] - corpus_hit), invest_after, fi["age"],
                        fi["annual_expenses"] + running_monthly * 12 * (1 if item_type in {"car", "bike", "home"} else 0),
                        retirement_age_target=snap["profile"]["retirement_age_target"], **kw)
    fire_delay = None
    if fire["fire_age"] is not None and f_after["fire_age"] is not None:
        fire_delay = round(f_after["fire_age"] - fire["fire_age"], 1)
    elif fire["fire_age"] is not None:
        fire_delay = float("inf")
    emi_ratio = new_emi_total / income * 100 if income else 0.0
    sr_after = new_surplus / income * 100 if income else 0.0

    reasons, verdict = [], "AFFORDABLE"

    def flag(level, text):
        nonlocal verdict
        reasons.append({"level": level, "text": text})
        if level == "block":
            verdict = "NOT ADVISABLE"
        elif level == "warn" and verdict == "AFFORDABLE":
            verdict = "STRETCH"

    if down > pool + 1:
        flag("block", f"Down payment ₹{down:,.0f} exceeds your liquid savings ₹{pool:,.0f}.")
    if emi_ratio > 50:
        flag("block", f"Total EMIs would be {emi_ratio:.0f}% of income (limit 50%).")
    elif emi_ratio > 40:
        flag("warn", f"Total EMIs would be {emi_ratio:.0f}% of income (comfortable limit 40%).")
    if new_surplus < 0:
        flag("block", f"You would run a monthly deficit of ₹{-new_surplus:,.0f}.")
    elif sr_after < 10:
        flag("warn", f"Savings rate would fall to {sr_after:.0f}% (target at least 10%).")
    if runway_after < 1:
        flag("block", f"Emergency runway would fall to {max(runway_after, 0):.1f} months (minimum 1).")
    elif runway_after < 3:
        flag("warn", f"Emergency runway would fall to {runway_after:.1f} months (target 3+).")
    if fire_delay is not None and fire_delay > 3:
        flag("warn", "Financial independence would be delayed by "
             + ("more than the projection horizon." if fire_delay == float("inf") else f"{fire_delay:.1f} years."))
    if item_type in {"car", "bike"} and price > 0.5 * income * 12:
        flag("warn", f"Vehicle price is {price / (income * 12) * 100:.0f}% of annual income (rule of thumb: under 50%).")
    if not reasons:
        reasons.append({"level": "ok", "text": "All affordability checks pass with room to spare."})
    return {
        "name": name, "price": round(price), "down_payment": round(down), "loan_amount": round(loan),
        "interest_rate_pct": rate, "tenure_months": months if loan > 0 else 0, "wait_months": wait_months,
        "emi": round(e), "total_interest": round(total_interest), "running_cost_monthly": round(running_monthly),
        "total_cost_of_ownership": round(price + total_interest + running_monthly * (months if loan > 0 else 60)),
        "tco_period_months": months if loan > 0 else 60,
        "impact": {
            "emi_to_income_pct": {"before": round(debt["emi_to_income_pct"] or 0, 1), "after": round(emi_ratio, 1)},
            "monthly_surplus": {"before": round(surplus), "after": round(new_surplus)},
            "savings_rate_pct": {"before": round(cf["avg_savings_rate_pct"] or 0, 1), "after": round(sr_after, 1)},
            "runway_months": {"before": round(runway_before, 1), "after": round(max(runway_after, 0), 1)},
            "liquid_savings": {"before": round(liq["emergency_pool"]), "after": round(pool_after)},
            "fire_age": {"before": fire["fire_age"], "after": f_after["fire_age"]},
            "fire_delay_years": None if fire_delay is None or fire_delay == float("inf") else fire_delay,
        },
        "verdict": verdict, "reasons": reasons,
    }


def simulate(ident: Identity, *, item_type: str, item_name: str, price: float, down_payment: float,
             interest_rate: float, tenure_months: int, running_cost_monthly: float | None = None,
             snap: dict | None = None) -> dict:
    snap = snap or build(ident)
    item_type = item_type.lower() if item_type.lower() in RUNNING_COST_DEFAULTS else "other"
    if running_cost_monthly is None:
        running_cost_monthly = price * RUNNING_COST_DEFAULTS[item_type] / 12
    base = dict(price=price, rate=interest_rate, months=tenure_months, running_monthly=running_cost_monthly, item_type=item_type)
    main = _scenario("Your plan", snap, down=down_payment, **base)
    pool = snap["liquidity"]["emergency_pool"]
    keep = 3 * snap["cash_flow"]["avg_monthly_expenses"]
    alts = []
    bigger = min(price, max(down_payment, pool - keep))
    if bigger > down_payment * 1.1 and bigger > 0:
        alts.append(_scenario("Bigger down payment (keep 3 months' runway)", snap, down=bigger, **base))
    if pool - price >= 0:
        alts.append(_scenario("Pay in full, no loan", snap, down=price, **{**base, "months": 0}))
    for w in (6, 12):
        alts.append(_scenario(f"Wait {w} months and save", snap, down=down_payment, wait_months=w, **base))
    if tenure_months >= 24:
        alts.append(_scenario(f"Shorter loan ({tenure_months // 2} months)", snap, down=down_payment,
                              **{**base, "months": tenure_months // 2}))
    order = {"AFFORDABLE": 0, "STRETCH": 1, "NOT ADVISABLE": 2}
    best = min([main] + alts, key=lambda s: (order[s["verdict"]], s["total_interest"] + s["wait_months"] * 1000))
    # what would make it affordable: highest price that passes all checks with this down payment share
    share = down_payment / price if price else 0
    lo, hi = 0.0, price
    for _ in range(30):
        mid = (lo + hi) / 2
        if mid <= 0:
            break
        s = _scenario("probe", snap, **{**base, "price": mid, "running_monthly": running_cost_monthly * mid / price}, down=mid * share)
        if s["verdict"] == "AFFORDABLE":
            lo = mid
        else:
            hi = mid
    return {"item": {"type": item_type, "name": item_name}, "plan": main, "alternatives": alts,
            "best_option": None if best["verdict"] == "NOT ADVISABLE" else best["name"], "max_affordable_price_same_terms": round(lo, -3),
            "verdict_rules": __doc__.split("Verdict rules")[1].strip(),
            "disclaimer": "Educational guidance, not a substitute for a licensed financial advisor."}

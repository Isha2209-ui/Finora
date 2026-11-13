"""FIRE (Financial Independence, Retire Early) engine.

All projections are in TODAY'S rupees ("real" terms): the corpus grows at the real return
(nominal return adjusted for inflation), and expenses stay at today's level. This keeps the
FIRE number and the projected corpus directly comparable.

  real_return  = (1 + nominal) / (1 + inflation) - 1
  FIRE number  = annual expenses / safe withdrawal rate
  corpus(t+1)  = corpus(t) * (1 + r_month) + monthly_investment(t)

Defaults: 11% nominal return, 6% inflation, 3.3% withdrawal rate (≈30x expenses; more
conservative than the US "4% rule" because Indian inflation is higher), 5% yearly step-up.
Monte Carlo: yearly real returns drawn from a normal distribution (mean = real return,
sd = 15% x equity share), fixed random seed so results are reproducible.
"""
from __future__ import annotations

import numpy as np

DEFAULTS = dict(nominal_return=0.11, inflation=0.06, swr=0.033, step_up=0.05, max_age=75,
                lean_factor=0.7, fat_factor=1.5, mc_runs=5000, equity_share=0.65, seed=42)


def real_rate(nominal: float, inflation: float) -> float:
    return (1 + nominal) / (1 + inflation) - 1


def future_value(pv: float, monthly: float, annual_rate: float, years: float, step_up: float = 0.0) -> float:
    """Closed-form when step_up == 0, otherwise month-by-month. Contributions at month end."""
    n = int(round(years * 12))
    i = (1 + annual_rate) ** (1 / 12) - 1
    if step_up == 0:
        return pv * (1 + i) ** n + (monthly * ((1 + i) ** n - 1) / i if i else monthly * n)
    v, m = pv, monthly
    for k in range(n):
        v = v * (1 + i) + m
        if (k + 1) % 12 == 0:
            m *= 1 + step_up
    return v


def project(corpus: float, monthly_investment: float, age: int, annual_expenses: float, *,
            retirement_age_target: int | None = None, **kw) -> dict:
    p = {**DEFAULTS, **{k: v for k, v in kw.items() if v is not None}}
    rr = real_rate(p["nominal_return"], p["inflation"])
    real_step = (1 + p["step_up"]) / (1 + p["inflation"]) - 1  # step-up in today's rupees
    fire_number = annual_expenses / p["swr"]
    targets = {"lean": fire_number * p["lean_factor"], "regular": fire_number, "fat": fire_number * p["fat_factor"]}

    i = (1 + rr) ** (1 / 12) - 1
    series, v, m = [], corpus, monthly_investment
    reached = {k: None for k in targets}
    for month in range(0, (p["max_age"] - age) * 12 + 1):
        a = age + month / 12
        if month % 12 == 0:
            series.append({"age": int(round(a)), "corpus": round(v), "fire_number": round(fire_number)})
        for k, tgt in targets.items():
            if reached[k] is None and v >= tgt:
                reached[k] = round(a, 1)
        v = v * (1 + i) + m
        if (month + 1) % 12 == 0:
            m *= 1 + real_step

    # Coast FIRE: corpus needed today that grows (with no new investment) to the FIRE number by age 60
    coast_age = 60
    yrs_to_coast = max(0, coast_age - age)
    coast_number = fire_number / (1 + rr) ** yrs_to_coast
    target_age = retirement_age_target
    corpus_at_target = None
    needed_monthly = None
    if target_age and target_age > age:
        yrs = target_age - age
        corpus_at_target = future_value(corpus, monthly_investment, rr, yrs, real_step)
        lo, hi = 0.0, max(1.0, fire_number / 12)
        for _ in range(50):
            mid = (lo + hi) / 2
            if future_value(corpus, mid, rr, yrs, real_step) < fire_number:
                lo = mid
            else:
                hi = mid
        needed_monthly = hi
    mc = monte_carlo(corpus, monthly_investment, age, target_age or 60, fire_number, rr, real_step, p)
    return {
        "inputs": {"current_corpus": round(corpus), "monthly_investment": round(monthly_investment), "age": age,
                   "annual_expenses": round(annual_expenses), "nominal_return_pct": round(p["nominal_return"] * 100, 2),
                   "inflation_pct": round(p["inflation"] * 100, 2), "real_return_pct": round(rr * 100, 2),
                   "withdrawal_rate_pct": round(p["swr"] * 100, 2), "annual_step_up_pct": round(p["step_up"] * 100, 2)},
        "fire_number": round(fire_number), "lean_fire_number": round(targets["lean"]),
        "fat_fire_number": round(targets["fat"]),
        "fire_age": reached["regular"], "lean_fire_age": reached["lean"], "fat_fire_age": reached["fat"],
        "years_to_fire": None if reached["regular"] is None else round(reached["regular"] - age, 1),
        "progress_pct": round(corpus / fire_number * 100, 1) if fire_number else None,
        "coast_fire_number": round(coast_number), "coast_fire_reached": corpus >= coast_number,
        "retirement_age_target": target_age,
        "corpus_at_target_age": None if corpus_at_target is None else round(corpus_at_target),
        "shortfall_at_target_age": None if corpus_at_target is None else round(max(0.0, fire_number - corpus_at_target)),
        "monthly_investment_needed_for_target": None if needed_monthly is None else round(needed_monthly, -2),
        "on_track": None if corpus_at_target is None else corpus_at_target >= fire_number,
        "success_probability_pct": mc["success_pct"], "monte_carlo": mc,
        "projection": series,
        "note": "All amounts are in today's rupees (inflation-adjusted).",
    }


def monte_carlo(corpus, monthly, age, target_age, fire_number, rr, real_step, p) -> dict:
    years = max(1, int(target_age - age))
    rng = np.random.default_rng(p["seed"])
    sd = 0.15 * p["equity_share"] + 0.03 * (1 - p["equity_share"])
    rets = rng.normal(rr, sd, size=(p["mc_runs"], years))
    v = np.full(p["mc_runs"], float(corpus))
    contrib = monthly * 12
    for y in range(years):
        v = v * (1 + rets[:, y]) + contrib * (1 + rets[:, y] / 2)  # contributions earn ~half-year return
        v = np.maximum(v, 0.0)
        contrib *= 1 + real_step
    return {"runs": p["mc_runs"], "target_age": target_age, "success_pct": round(float((v >= fire_number).mean() * 100), 1),
            "p10": round(float(np.percentile(v, 10))), "p50": round(float(np.percentile(v, 50))),
            "p90": round(float(np.percentile(v, 90))), "return_sd_pct": round(sd * 100, 1)}


def corpus_by_age(corpus: float, monthly: float, age: int, ages: list[int], **kw) -> list[dict]:
    p = {**DEFAULTS, **{k: v for k, v in kw.items() if v is not None}}
    rr = real_rate(p["nominal_return"], p["inflation"])
    real_step = (1 + p["step_up"]) / (1 + p["inflation"]) - 1
    out = []
    for a in ages:
        if a <= age:
            continue
        real = future_value(corpus, monthly, rr, a - age, real_step)
        nominal = real * (1 + p["inflation"]) ** (a - age)
        out.append({"age": a, "corpus_todays_rupees": round(real), "corpus_future_rupees": round(nominal)})
    return out

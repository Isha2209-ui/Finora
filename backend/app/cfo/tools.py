"""Tools the AI CFO can call. Every number the assistant states must come from one of these.

Each tool takes the person's current analysis (and identity where needed) and returns a
small JSON-serialisable dict. The language model never does arithmetic itself.
"""
from __future__ import annotations

from ..services import calculations as C
from ..services import decision as D
from ..services import fire as F
from ..services import tax as T


def _pick(d: dict, keys: list[str]) -> dict:
    return {k: d.get(k) for k in keys}


def profile_summary(ctx, **_):
    a = ctx["analysis"]
    return {"name": a["profile"]["name"], "age": a["profile"]["age"], "occupation": a["profile"]["occupation"],
            "net_worth": a["net_worth"]["net_worth"], "total_assets": a["net_worth"]["total_assets"],
            "total_liabilities": a["net_worth"]["total_liabilities"],
            "avg_monthly_income": a["cash_flow"]["avg_monthly_income"], "avg_monthly_expenses": a["cash_flow"]["avg_monthly_expenses"],
            "savings_rate_pct": a["cash_flow"]["avg_savings_rate_pct"], "health_score": a["health_score"]["score"],
            "health_band": a["health_score"]["band"], "health_pillars": a["health_score"]["pillars"],
            "income_known": a["cash_flow"].get("income_known", True), "spending_known": a["cash_flow"].get("spending_known", True),
            "missing_data": (a.get("completeness") or {}).get("missing", [])}


def cash_flow(ctx, **_):
    cf = ctx["analysis"]["cash_flow"]
    out = _pick(cf, ["avg_monthly_income", "avg_monthly_expenses", "avg_monthly_savings", "avg_savings_rate_pct",
                     "essential_to_income_pct", "discretionary_to_income_pct", "emi_to_income_pct", "months_in_deficit",
                     "latest_month", "monthly_expenses", "expense_change_pct"])
    out["top_categories"] = [{"category": c["category"], "monthly_avg": c["monthly_avg"], "share_pct": c["share_of_spend_pct"]}
                             for c in cf["category_totals"][:6]]
    out["last_3_months"] = [_pick(m, ["month", "income", "expenses", "savings"]) for m in cf["monthly_series"][-3:]]
    out["income_known"], out["spending_known"] = cf.get("income_known", True), cf.get("spending_known", True)
    return out


def spending_by_category(ctx, category: str | None = None, **_):
    if not ctx["analysis"]["cash_flow"].get("spending_known", True):
        return {"available": False}
    cats = ctx["analysis"]["cash_flow"]["category_totals"]
    if category:
        hit = [c for c in cats if c["category"].lower() == category.lower()]
        if hit:
            lim = [l for l in ctx["analysis"]["budget"]["category_limits"] if l["category"] == hit[0]["category"]]
            return {"category": hit[0]["category"], "monthly_avg": hit[0]["monthly_avg"], "total_12m": hit[0]["total"],
                    "share_of_spend_pct": hit[0]["share_of_spend_pct"], **({"last_3m_avg": lim[0]["last_3m_avg"],
                                                                            "suggested_limit": lim[0]["suggested_limit"]} if lim else {})}
    return {"categories": [{"category": c["category"], "monthly_avg": c["monthly_avg"], "share_pct": c["share_of_spend_pct"]} for c in cats[:8]],
            "budget_scenarios": ctx["analysis"]["budget"]["scenarios"]}


def net_worth(ctx, **_):
    nw = ctx["analysis"]["net_worth"]
    return {**_pick(nw, ["net_worth", "total_assets", "total_liabilities", "breakdown", "liabilities", "change_over_period"]),
            "allocation_pct": ctx["analysis"]["allocation"]["allocation_pct"]}


def investments(ctx, **_):
    inv = ctx["analysis"]["investments"]
    return {**_pick(inv, ["total_invested", "current_value", "total_gain", "total_gain_pct", "sip_monthly_total",
                          "sip_to_income_pct", "sips_missed_last_12m", "top_sector", "top_holding", "losing_positions"]),
            "top_holdings": [_pick(h, ["name", "current", "gain_pct"]) for h in inv["holdings"][:5]],
            "equity_pct_of_financial_assets": ctx["analysis"]["allocation"]["financial_assets_equity_pct"],
            "suggested_equity_pct_for_age": ctx["analysis"]["allocation"]["suggested_equity_pct_for_age"]}


def credit_cards(ctx, **_):
    cr = ctx["analysis"]["credit"]
    if not cr.get("has_cards"):
        return {"has_cards": False}
    risk = ctx["analysis"]["ml"].get("credit_risk", {})
    return {"overall_utilisation_pct": cr["overall_utilisation_pct"], "total_outstanding": cr["total_outstanding"],
            "total_limit": cr["total_limit"], "est_interest_per_month": cr["est_interest_per_month"],
            "cards": [_pick(c, ["card", "outstanding", "limit", "utilisation_pct", "min_due", "due_day",
                                "months_paid_minimum_only_last6", "months_delayed_last6"]) for c in cr["cards"]],
            "default_risk_pct": risk.get("overall_default_probability_pct"), "default_risk_band": risk.get("overall_risk_band")}


def debts_and_payoff(ctx, extra_monthly: float = 0.0, **_):
    d = ctx["analysis"]["debt"]
    if not d["has_debt"]:
        return {"has_debt": False}
    debts = [{"name": x["name"], "balance": x["balance"], "rate": x["rate"], "payment": x["payment"]} for x in d["debts"]]
    plan = C.payoff_strategies(debts, float(extra_monthly or 0))
    return {"total_debt": d["total_debt"], "total_emi": d["total_emi"], "emi_to_income_pct": d["emi_to_income_pct"],
            "risk_band": d["risk_band"], "weighted_avg_rate_pct": d["weighted_avg_rate_pct"],
            "highest_rate_debt": d["highest_rate_debt"], "debts": debts, "extra_monthly_payment": plan["extra_monthly_payment"],
            "avalanche_months": plan["avalanche"]["months_to_debt_free"], "avalanche_interest": plan["avalanche"]["total_interest"],
            "snowball_months": plan["snowball"]["months_to_debt_free"], "snowball_interest": plan["snowball"]["total_interest"],
            "interest_saved_by_avalanche": plan["interest_saved_by_avalanche"],
            "first_to_clear": plan["avalanche"]["payoff_order"][0]["debt"] if plan["avalanche"]["payoff_order"] else None,
            "loans": [{"loan": l.get("loan_type"), "lender": l.get("lender"), "original_principal": l.get("principal"),
                       "outstanding_balance": l.get("balance"), "emi": l.get("emi"), "remaining_months": l.get("remaining_months")}
                      for l in ctx["identity"].loans]}


def runway(ctx, **_):
    l = ctx["analysis"]["liquidity"]
    return _pick(l, ["runway_months", "runway_months_essentials_only", "runway_months_incl_market", "emergency_pool",
                     "emergency_fund_months", "emergency_fund_gap", "immediate", "within_a_week"]) | \
        {"avg_monthly_expenses": ctx["analysis"]["cash_flow"]["avg_monthly_expenses"],
         "expenses_known": ctx["analysis"]["cash_flow"].get("spending_known", True)}


def fire_forecast(ctx, monthly_investment: float | None = None, retirement_age: int | None = None,
                  annual_expenses: float | None = None, nominal_return_pct: float | None = None, **_):
    f = ctx["analysis"]["fire"]
    fi = f["inputs"]
    if not f.get("available", True) and annual_expenses is None:
        return {"available": False, "reason": f["reason"], "current_corpus": fi["current_corpus"],
                "monthly_investment": fi["monthly_investment"]}
    changed = any(v is not None for v in (monthly_investment, retirement_age, annual_expenses, nominal_return_pct))
    if changed:
        f = F.project(fi["current_corpus"], monthly_investment if monthly_investment is not None else fi["monthly_investment"],
                      fi["age"], annual_expenses if annual_expenses is not None else fi["annual_expenses"],
                      retirement_age_target=retirement_age or ctx["analysis"]["profile"]["retirement_age_target"],
                      nominal_return=(nominal_return_pct / 100 if nominal_return_pct else fi["nominal_return_pct"] / 100),
                      inflation=fi["inflation_pct"] / 100, swr=fi["withdrawal_rate_pct"] / 100, step_up=fi["annual_step_up_pct"] / 100)
    out = _pick(f, ["fire_number", "lean_fire_number", "fat_fire_number", "fire_age", "lean_fire_age", "fat_fire_age",
                    "years_to_fire", "progress_pct", "coast_fire_number", "coast_fire_reached", "retirement_age_target",
                    "corpus_at_target_age", "shortfall_at_target_age", "monthly_investment_needed_for_target", "on_track",
                    "success_probability_pct"])
    out["inputs"] = f["inputs"]
    out["what_if"] = changed
    if not changed:
        out["if_you_invested_80pct_of_surplus"] = f.get("if_you_invested_80pct_of_surplus")
    return out


def affordability(ctx, price: float, down_payment: float | None = None, interest_rate: float | None = None,
                  tenure_months: int | None = None, item_type: str = "other", item_name: str | None = None, **_):
    defaults = {"car": (9.5, 60), "bike": (11.0, 36), "home": (8.75, 240), "phone": (15.0, 12), "gadget": (15.0, 12),
                "trip": (14.0, 12), "education": (10.5, 84), "wedding": (13.0, 36), "other": (12.0, 36)}
    r, n = defaults.get(item_type, defaults["other"])
    price = float(price)
    dp = float(down_payment) if down_payment is not None else round(price * 0.2, -3)
    res = D.simulate(ctx["identity"], item_type=item_type, item_name=item_name or item_type.title(), price=price,
                     down_payment=dp, interest_rate=float(interest_rate) if interest_rate is not None else r,
                     tenure_months=int(tenure_months) if tenure_months else n, snap=ctx["analysis"])
    if not res.get("available", True):
        return {"available": False, "item": res["item"]["name"], "price": round(price), "missing": res["missing"]}
    p = res["plan"]
    return {"item": res["item"]["name"], "price": p["price"], "down_payment": p["down_payment"], "loan_amount": p["loan_amount"],
            "interest_rate_pct": p["interest_rate_pct"], "tenure_months": p["tenure_months"], "emi": p["emi"],
            "total_interest": p["total_interest"], "running_cost_monthly": p["running_cost_monthly"],
            "verdict": p["verdict"], "reasons": [x["text"] for x in p["reasons"]], "impact": p["impact"],
            "best_option": res["best_option"], "max_affordable_price_same_terms": res["max_affordable_price_same_terms"],
            "alternatives": [{"name": a["name"], "verdict": a["verdict"], "emi": a["emi"], "total_interest": a["total_interest"]} for a in res["alternatives"]],
            "assumed_defaults": {"down_payment": down_payment is None, "interest_rate": interest_rate is None, "tenure": tenure_months is None}}


def emi_calculator(ctx, principal: float, interest_rate: float = 10.0, tenure_months: int = 60, **_):
    e = D.emi(float(principal), float(interest_rate), int(tenure_months))
    return {"principal": round(float(principal)), "interest_rate_pct": float(interest_rate), "tenure_months": int(tenure_months),
            "emi": round(e), "total_interest": round(e * int(tenure_months) - float(principal)),
            "total_payment": round(e * int(tenure_months))}


def tax_comparison(ctx, gross_income: float | None = None, **_):
    if gross_income:
        t = T.compare(float(gross_income), ctx["analysis"]["profile"]["employment_type"] == "salaried")
    else:
        t = ctx["analysis"]["tax"]
        if not t.get("available", True):
            return {"available": False}
    return {"financial_year": t["financial_year"], "gross_income": t["gross_income"], "new_regime_tax": t["new"]["total_tax"],
            "old_regime_tax": t["old"]["total_tax"], "old_regime_deductions_used": t["old"]["deductions"],
            "better_regime": t["better_regime"], "saving_with_better": t["saving_with_better"],
            "old_regime_breakeven_deductions": t["old_regime_breakeven_deductions"],
            "new_regime_standard_deduction": t["new"]["standard_deduction"]}


def spending_forecast(ctx, **_):
    f = ctx["analysis"]["ml"].get("forecast", {})
    if not f.get("available"):
        return {"available": False}
    return {**_pick(f, ["prediction_month", "predicted_total_expense", "range", "last_month_actual", "change_vs_last_month_pct",
                        "expected_income", "projected_surplus", "projected_status", "projected_bank_balance_end_of_month",
                        "top_increase_drivers"]),
            "categories": [_pick(c, ["category", "predicted", "three_month_avg", "suggested_budget", "trend"]) for c in f["category_predictions"][:6]]}


def unusual_transactions(ctx, **_):
    a = ctx["analysis"]["ml"].get("anomaly", {})
    return {"transactions_scored": a.get("transactions_scored", 0), "flagged_count": a.get("flagged_count", 0), "flagged_amount_total": a.get("flagged_amount_total", 0),
            "transactions": [_pick(f, ["date", "merchant", "category", "amount", "typical_amount", "times_typical", "severity", "source"])
                             for f in a.get("flagged", [])[:6]]}


def recommendations(ctx, **_):
    return {"recommendations": [_pick(r, ["priority", "finding", "action", "impact_text"]) for r in ctx["analysis"]["recommendations"][:6]]}


def insurance(ctx, **_):
    return _pick(ctx["analysis"]["insurance"], ["term_cover", "recommended_term_cover", "term_gap", "health_cover",
                                                "recommended_health_cover", "health_gap", "has_term", "has_health"])


def goals(ctx, **_):
    return {"goals": ctx["analysis"]["goals"]}


def peer_comparison(ctx, **_):
    p = ctx["analysis"]["ml"].get("peers", {})
    if not p.get("available", True) or not p.get("peer_group"):
        return {"available": False, "note": p.get("note")}
    return _pick(p, ["peer_group", "strengths", "weaknesses"]) | {"comparison": p.get("comparison", [])[:5]}


REGISTRY = {
    "profile_summary": (profile_summary, "Overall financial picture: net worth, income, expenses, savings rate, health score.", {}),
    "cash_flow": (cash_flow, "Income, expenses, savings and top spending categories.", {}),
    "spending_by_category": (spending_by_category, "Spending for one category or all categories, with budget scenarios.",
                             {"category": ("string", "Category name, e.g. Dining, Shopping, Travel")}),
    "net_worth": (net_worth, "Assets, liabilities, net worth and asset allocation.", {}),
    "investments": (investments, "Portfolio value, gains, SIPs, concentration.", {}),
    "credit_cards": (credit_cards, "Card balances, utilisation, interest and default risk.", {}),
    "debts_and_payoff": (debts_and_payoff, "All debts and the fastest/cheapest payoff plan.",
                         {"extra_monthly": ("number", "Extra rupees per month to put toward debt")}),
    "runway": (runway, "ALWAYS use for 'how long would my savings last', 'if I lost my job', emergency fund: months of runway.", {}),
    "fire_forecast": (fire_forecast, "Financial independence / retirement projection, optionally with what-if changes.",
                      {"monthly_investment": ("number", "What-if monthly investment in rupees"),
                       "retirement_age": ("integer", "What-if target retirement age"),
                       "annual_expenses": ("number", "What-if annual expenses in retirement"),
                       "nominal_return_pct": ("number", "What-if expected annual return in percent")}),
    "affordability": (affordability, "ALWAYS use for 'can I afford <item>' (car, bike, home, phone, holiday/trip, wedding, education): "
                                     "EMI, impact on surplus, savings and investments, verdict and cheaper alternatives.",
                      {"price": ("number", "Price in rupees"), "down_payment": ("number", "Down payment in rupees"),
                       "interest_rate": ("number", "Loan interest rate percent"), "tenure_months": ("integer", "Loan tenure in months"),
                       "item_type": ("string", "car, bike, home, phone, gadget, trip, education, wedding or other"),
                       "item_name": ("string", "Name of the item")}),
    "emi_calculator": (emi_calculator, "EMI for any loan amount, rate and tenure.",
                       {"principal": ("number", "Loan amount in rupees"), "interest_rate": ("number", "Annual rate percent"),
                        "tenure_months": ("integer", "Tenure in months")}),
    "tax_comparison": (tax_comparison, "ALWAYS use for income tax and 'which tax regime' (old vs new regime, FY 2026-27).",
                       {"gross_income": ("number", "Annual gross income in rupees (optional)")}),
    "spending_forecast": (spending_forecast, "ML forecast of next month's spending and cash position.", {}),
    "unusual_transactions": (unusual_transactions, "Transactions flagged as unusual by the anomaly model.", {}),
    "recommendations": (recommendations, "Top prioritised recommendations.", {}),
    "insurance": (insurance, "Life and health insurance cover and gaps.", {}),
    "goals": (goals, "Progress on financial goals.", {}),
    "peer_comparison": (peer_comparison, "Comparison with similar people.", {}),
}


def ollama_schema() -> list[dict]:
    out = []
    for name, (_, desc, params) in REGISTRY.items():
        if name in HIDDEN_FROM_LLM:
            continue
        out.append({"type": "function", "function": {"name": name, "description": desc, "parameters": {
            "type": "object", "properties": {k: {"type": t, "description": d} for k, (t, d) in params.items()},
            "required": REQUIRED.get(name, [])}}})
    return out


def call(name: str, ctx: dict, args: dict | None = None) -> dict:
    if name not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    fn, _, params = REGISTRY[name]
    clean = {}
    for k, v in (args or {}).items():
        if k in params and v not in (None, ""):
            try:
                clean[k] = int(float(v)) if params[k][0] == "integer" else float(v) if params[k][0] == "number" else str(v)
            except (TypeError, ValueError):
                continue
    try:
        return fn(ctx, **clean)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ================================================================ Phase 7 tools (read-only, bound to the signed-in profile)
# Every tool receives `ctx` built by the server for the AUTHENTICATED account's selected profile. No tool accepts a user,
# profile, file, SQL or URL argument, so the model cannot reach another person's data or anything outside Finora's services.
import re
from datetime import date as _date

import pandas as _pd

from ..services.cleaning import ALL_CATEGORIES as _ALL_CATS, NON_EXPENSE as _NON_EXPENSE, clean_transactions as _clean, \
    standardise_category as _std_cat

PERIODS = ["this_month", "last_month", "last_3_months", "last_6_months", "last_12_months", "all"]


def _today() -> _date:
    return _date.today()


def _months_back(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _period_months(period: str | None, available: list[str]) -> tuple[list[str], str]:
    """Calendar months for a period, relative to TODAY (not to the data). Returns (months, description)."""
    cur = _today().strftime("%Y-%m")
    p = (period or "last_month").strip().lower().replace(" ", "_")
    if len(p) == 7 and p[4] == "-" and p[:4].isdigit() and p[5:].isdigit():
        return [p], p
    if len(p) == 4 and p.isdigit() and 1900 < int(p) <= int(cur[:4]):          # a calendar year
        return [f"{p}-{m:02d}" for m in range(1, 13) if f"{p}-{m:02d}" <= cur], f"calendar year {p}"
    if p == "this_month":
        return [cur], f"{cur} (month to date)"
    if p == "last_month":
        m = _months_back(cur, 1)
        return [m], m
    n = {"last_3_months": 3, "last_6_months": 6, "last_12_months": 12}.get(p)
    if n:
        ms = [_months_back(cur, i) for i in range(n, 0, -1)]
        return ms, f"{ms[0]} to {ms[-1]}"
    if p in ("all", "all_time", "everything", "history"):
        return sorted(available), "all recorded history"
    raise ValueError(f"unknown period '{str(period)[:40]}': use {', '.join(PERIODS)}, YYYY-MM or YYYY")


def _tx(ctx) -> _pd.DataFrame:
    tx = ctx["identity"].transactions
    if tx is None or len(tx) == 0:
        return _pd.DataFrame(columns=["date", "month", "amount", "type", "category", "spend", "merchant", "raw_description"])
    t, _ = _clean(tx)
    return t


def spending(ctx, period: str | None = None, category: str | None = None, merchant: str | None = None, **_):
    t = _tx(ctx)
    avail = sorted(t["month"].unique().tolist()) if len(t) else []
    try:
        months, desc = _period_months(period, avail)
    except ValueError as e:
        return {"error": str(e), "periods": PERIODS}
    out = {"period": desc, "months": months, "data_covers": f"{avail[0]} to {avail[-1]}" if avail else "no transactions recorded"}
    if not len(t):
        return {**out, "available": False, "note": "No transactions are recorded for this profile."}
    s = t[t["month"].isin(months) & (t["spend"] != 0)]
    if category and str(category).strip().lower() in ("all", "any", "total", "everything", "none", "*"):
        category = None
    if category:
        cat = _std_cat(category)
        if cat in _NON_EXPENSE:                  # investments, own transfers, card bills: money moved, not spending
            mv = t[t["month"].isin(months) & (t["category"] == cat) & (t["type"] == "debit")]
            return {**out, "category": cat, "money_moved_not_spending": round(float(mv["amount"].sum()), 2),
                    "transactions": int(len(mv)), "note": f"{cat} is money moved, not spending, so it is excluded from spending totals."}
        if cat in _ALL_CATS or cat == "Uncategorised":
            s = s[s["category"] == cat]
            out["category"] = cat
        elif not merchant:                       # not a category: search merchants and descriptions for the words instead
            merchant = str(category)
            out["note_category"] = f"'{category}' is not a Finora category, so merchants and descriptions were searched for it. " \
                                   f"Categories: {', '.join(_ALL_CATS)}"
    if merchant:
        words = [w for w in re.split(r"[^A-Z0-9]+", str(merchant).upper()) if len(w) >= 3 and w not in ("SHOP", "SHOPS", "STORE", "STORES")]
        text_ = s["merchant"].fillna("").str.upper() + " " + s["raw_description"].fillna("").str.upper()
        hit = _pd.Series(False, index=s.index)
        for w in words or [str(merchant).upper()]:
            hit |= text_.str.contains(w.rstrip("S"), regex=False)
        s = s[hit]
        out["merchant"] = merchant
    out.update({"total_spent": round(float(s["spend"].sum()), 2), "transactions": int((s["type"] == "debit").sum()),
                "refunds_netted": round(float(-s.loc[s["spend"] < 0, "spend"].sum()), 2)})
    if not category:
        by = s.groupby("category")["spend"].sum().sort_values(ascending=False)
        out["by_category"] = [{"category": k, "amount": round(float(v), 2)} for k, v in by.head(10).items()]
    names = s["merchant"].fillna(s["raw_description"])
    top = s.assign(n=names).groupby("n")["spend"].sum().sort_values(ascending=False).head(5)
    out["top_merchants"] = [{"merchant": k, "amount": round(float(v), 2)} for k, v in top.items()]
    if len(months) == 1:
        out["month_name"] = _date(int(months[0][:4]), int(months[0][5:]), 1).strftime("%B %Y")
        per = t[t["month"] == months[0]]
        out["months_without_data"] = [] if len(per) else months
    else:
        out["months_without_data"] = [m for m in months if m not in avail]
    out["note"] = "Spending excludes money moved (card bill payments, own transfers, investments); refunds reduce spending."
    return out


def income(ctx, period: str | None = None, **_):
    inc = ctx["identity"].income
    if inc is None or len(inc) == 0:
        return {"available": False, "note": "No income is recorded for this profile."}
    i = inc.assign(month=_pd.to_datetime(inc["date"]).dt.strftime("%Y-%m"))
    avail = sorted(i["month"].unique().tolist())
    try:
        months, desc = _period_months(period, avail)
    except ValueError as e:
        return {"error": str(e), "periods": PERIODS}
    s = i[i["month"].isin(months)]
    by = s.groupby("source")["amount"].sum().sort_values(ascending=False)
    return {"period": desc, "total_income": round(float(s["amount"].sum()), 2), "by_source": [{"source": k, "amount": round(float(v), 2)} for k, v in by.items()],
            "data_covers": f"{avail[0]} to {avail[-1]}", "months_without_data": [m for m in months if m not in avail]}


def compare_months(ctx, month: str | None = None, previous: str | None = None, **_):
    t = _tx(ctx)
    inc = ctx["identity"].income
    cur = month or _months_back(_today().strftime("%Y-%m"), 1)
    prev = previous or _months_back(cur, 1)

    def one(m):
        s = t[(t["month"] == m) & (t["spend"] != 0)] if len(t) else t
        inc_m = 0.0
        if inc is not None and len(inc):
            inc_m = float(inc[_pd.to_datetime(inc["date"]).dt.strftime("%Y-%m") == m]["amount"].sum())
        by = s.groupby("category")["spend"].sum() if len(s) else _pd.Series(dtype=float)
        return {"month": m, "spent": round(float(s["spend"].sum()) if len(s) else 0.0, 2), "income": round(inc_m, 2),
                "saved": round(inc_m - (float(s["spend"].sum()) if len(s) else 0.0), 2), "by_category": {k: round(float(v), 2) for k, v in by.items()}}
    a, b = one(cur), one(prev)
    avail = sorted(t["month"].unique().tolist()) if len(t) else []
    missing = [m for m in (cur, prev) if m not in avail]
    if missing:
        return {"error": f"no transactions recorded for {', '.join(missing)}", "data_covers": f"{avail[0]} to {avail[-1]}" if avail else "none",
                "hint": "compare months inside data_covers, e.g. the latest two"}
    cats = sorted(set(a["by_category"]) | set(b["by_category"]))
    changes = sorted(({"category": c, "change": round(a["by_category"].get(c, 0) - b["by_category"].get(c, 0), 2)} for c in cats),
                     key=lambda x: -abs(x["change"]))
    return {"month": {k: a[k] for k in ("month", "spent", "income", "saved")}, "previous": {k: b[k] for k in ("month", "spent", "income", "saved")},
            "spending_change": round(a["spent"] - b["spent"], 2), "biggest_category_changes": changes[:6],
            "rising": [x for x in changes if x["change"] > 0][:5], "falling": [x for x in changes if x["change"] < 0][:5],
            "data_covers": f"{avail[0]} to {avail[-1]}"}


def accounts_and_balances(ctx, **_):
    ident = ctx["identity"]
    return {"bank_accounts": [{"bank": a.get("bank_name"), "account": a.get("account_masked"), "type": a.get("account_type"),
                               "balance": a.get("balance")} for a in ident.accounts],
            "total_bank_balance": round(sum((a.get("balance") or 0) for a in ident.accounts), 2),
            "credit_cards": [{"card": f"{c.get('issuer')} {c.get('card_name')}", "last4": c.get("last4"), "outstanding": c.get("outstanding"),
                              "limit": c.get("credit_limit")} for c in ident.cards],
            "loans": [{"loan": l.get("loan_type"), "lender": l.get("lender"), "original_principal": l.get("principal"),
                       "outstanding_balance": l.get("balance"), "emi": l.get("emi"), "rate_pct": l.get("interest_rate"),
                       "remaining_months": l.get("remaining_months")} for l in ident.loans]}


def credit_risk(ctx, **_):
    r = ctx["analysis"]["ml"].get("credit_risk", {})
    if not r.get("cards"):
        return {"available": False, "note": r.get("note") or "No card history to score."}
    return {"overall_default_probability_pct": r["overall_default_probability_pct"], "overall_risk_band": r["overall_risk_band"],
            "driven_by_card": r.get("driven_by_card"), "population_base_rate_pct": r.get("population_base_rate_pct"),
            "cards": [{"card": c["card"], "default_probability_pct": c["default_probability_pct"], "risk_band": c["risk_band"],
                       "top_shap_factors": c["top_factors"]} for c in r["cards"]],
            "model": "XGBoost + SHAP, test ROC-AUC 0.783 (logistic regression 0.760)", "status": (r.get("model_info") or {}).get("status"),
            "limitation": "XGBoost + SHAP estimate from a model trained on 30,000 real card accounts (Taiwan): a probability of a missed payment, not a credit-bureau score."}


def anomaly_scan(ctx, **_):
    a = ctx["analysis"]["ml"].get("anomaly", {})
    if a.get("available") is False:
        return {"available": False, "note": a.get("note")}
    return {"transactions_scanned": a.get("transactions_scored", 0), "flagged_count": a.get("flagged_count", 0),
            "flagged_amount_total": a.get("flagged_amount_total", 0),
            "flagged": [_pick(f, ["date", "merchant", "category", "amount", "typical_amount", "times_typical", "severity", "anomaly_score", "reasons"])
                        for f in a.get("flagged", [])[:8]],
            "threshold": (a.get("score_distribution") or {}).get("threshold"),
            "status": (a.get("model_info") or {}).get("status"),
            "limitation": "Isolation Forest: a flag means the transaction is unusual compared with this person's own history."}


def cash_flow_forecast(ctx, **_):
    f = ctx["analysis"]["ml"].get("forecast", {})
    if not f.get("available"):
        return {"available": False, "note": f.get("note")}
    info = f.get("model_info") or {}
    ev = info.get("evaluation") or {}
    return {**_pick(f, ["prediction_month", "predicted_total_expense", "range", "last_month_actual", "three_month_avg",
                        "change_vs_last_month_pct", "expected_income", "projected_surplus", "projected_status",
                        "projected_bank_balance_end_of_month"]),
            "baseline_three_month_average": f.get("three_month_avg"), "status": info.get("status"),
            "measured_error": ev,
            "limitation": "XGBoost forecast trained on a real personal account, shown beside a simple 3-month average"
                          + (f" (test error £{ev['xgboost_mae']:,.2f} for the model vs £{ev['baseline_3m_average_mae']:,.2f} for the average, in pounds)"
                             if ev.get("xgboost_mae") is not None and ev.get("baseline_3m_average_mae") is not None else "")
                          + "."}


def peer_benchmark(ctx, **_):
    p = ctx["analysis"]["ml"].get("peers", {})
    if not p.get("available", True) or not p.get("peer_group"):
        return {"available": False, "note": p.get("note")}
    return {**_pick(p, ["peer_group", "peer_group_share_pct", "strengths", "weaknesses", "units"]),
            "comparison": p.get("comparison", []),
            "limitation": "K-Means peer groups from US households (Federal Reserve SCF 2022); survey income is gross, Finora sees take-home pay."}


def category_suggestions(ctx, **_):
    tx = ctx["identity"].transactions
    if tx is None or len(tx) == 0 or "category_source" not in tx:
        return {"pending_suggestions": 0}
    s = tx[(tx["category_source"] == "model") & (tx["needs_review"].fillna(False).astype(bool))]
    return {"pending_suggestions": int(len(s)),
            "examples": [{"description": r["raw_description"], "suggested": r["category"], "confidence": r.get("confidence")}
                         for _, r in s.head(6).iterrows()],
            "how_to_confirm": "Accept, reject or change each suggestion on the Transactions or Review page; the assistant cannot change categories.",
            "limitation": "Categories suggested by the TF-IDF categoriser; each one waits for the user to accept or correct it."}


def finora_plan(ctx, **_):
    from ..services import plan as PL
    p = PL.build(ctx["analysis"], ctx.get("goals", []), ctx.get("accepted", []), ctx.get("dismissed", set()))
    if not p.get("available"):
        return {"available": False, "reason": p.get("reason")}
    return {"diagnosis": [{k: d.get(k) for k in ("finding", "evidence", "why", "why_it_matters") if d.get(k) is not None}
                          for d in p.get("diagnosis", [])[:6]],
            "ranked_actions": [_pick(x, ["title", "kind_label", "params", "impact", "effect", "status"]) for x in p.get("actions", [])[:5]],
            "accepted_assumptions": [_pick(x, ["title", "kind", "params"]) for x in ctx.get("accepted", [])],
            "with_plan": p.get("with_plan"), "baseline": p.get("baseline"), "method": p.get("method", {}).get("ranking")}


def plan_what_if(ctx, kind: str, amount: float | None = None, category: str | None = None, months_delay: int | None = None,
                 goal_name: str | None = None, **_):
    """The Finora Plan scenario engine (nothing is saved)."""
    from ..services import plan as PL
    if kind not in PL.KINDS:
        return {"error": f"kind must be one of {list(PL.KINDS)}"}
    params: dict = {}
    if kind == "delayed_purchase":
        g = next((g for g in ctx.get("goals", []) if not goal_name or g["name"].lower() == str(goal_name).lower()), None)
        if g is None:
            return {"error": "no matching goal", "goals": [x["name"] for x in ctx.get("goals", [])]}
        params = {"goal_id": g["id"], "months_delay": int(months_delay or 6)}
    else:
        if not amount or amount <= 0 or amount > 10_000_000:
            return {"error": "amount must be a positive monthly rupee amount up to 1 crore"}
        params = {"amount": float(amount)}
        if kind == "spending_cap" and category:
            params["category"] = _std_cat(category)
    b = PL.base_from(ctx["analysis"], ctx.get("goals", []))
    base, scen = PL.evaluate(b, []), PL.evaluate(b, [{"kind": kind, "params": params}])
    return {"kind": PL.KINDS[kind], "params": params, "baseline": PL._metrics(base), "scenario": PL._metrics(scen),
            "effect": PL.compare(base, scen), "saved": False,
            "note": "A what-if only: nothing is changed. Accepting it into the plan is done on the Finora Plan page."}


def alerts(ctx, **_):
    return {"alerts": ctx["analysis"].get("alerts", [])[:8]}


REGISTRY.update({
    "spending": (spending, "The user's actual spending from stored transactions for a period, optionally one category or merchant; "
                           "totals, by category, top merchants.",
                 {"period": ("string", "this_month, last_month, last_3_months, last_6_months, last_12_months, all, or a month YYYY-MM"),
                  "category": ("string", "optional category, e.g. Dining (food), Groceries, Shopping, Travel, Fuel, Utilities"),
                  "merchant": ("string", "optional merchant name, e.g. Swiggy")}),
    "income": (income, "The user's recorded income for a period, by source.",
               {"period": ("string", "this_month, last_month, last_3_months, last_6_months, last_12_months, all, or YYYY-MM")}),
    "compare_months": (compare_months, "Compare spending, income and savings of two months, with the biggest category changes. "
                                       "Defaults: last month vs the month before.",
                       {"month": ("string", "YYYY-MM"), "previous": ("string", "YYYY-MM to compare against")}),
    "accounts_and_balances": (accounts_and_balances, "Bank accounts and balances, credit cards with outstanding and limit, loans.", {}),
    "credit_risk": (credit_risk, "ALWAYS use for 'credit risk', 'default risk', 'credit profile', 'why did the model give that': the credit-risk "
                                 "model result per card with SHAP factors and limitations.", {}),
    "anomaly_scan": (anomaly_scan, "ALWAYS use for unusual, suspicious, strange or fraud-like transactions: the Anomaly Detection Scanner's flags, "
                                   "scores, reasons and experimental status.", {}),
    "cash_flow_forecast": (cash_flow_forecast, "ALWAYS use for the forecast, next month's spending or money available next month, and how "
                                               "reliable the forecast is: experimental XGBoost forecast, 3-month-average baseline, measured error.", {}),
    "peer_benchmark": (peer_benchmark, "ALWAYS use for 'compare with people like me', peers, others, 'am I normal': the user's ratios vs US "
                                       "household peer groups (SCF 2022), with limitations.", {}),
    "category_suggestions": (category_suggestions, "Pending transaction-category suggestions from the categoriser awaiting the user's confirmation.", {}),
    "finora_plan": (finora_plan, "The Finora Plan: diagnosis, ranked next actions and accepted plan assumptions.", {}),
    "plan_what_if": (plan_what_if, "What-if with the Finora Plan scenario engine (nothing is saved): new SIP, extra debt repayment, "
                                   "spending cap, emergency-fund contribution or delayed purchase. Returns baseline vs scenario.",
                     {"kind": ("string", "sip, extra_debt_repayment, spending_cap, emergency_fund_contribution or delayed_purchase"),
                      "amount": ("number", "monthly rupee amount"), "category": ("string", "for spending_cap"),
                      "months_delay": ("integer", "for delayed_purchase"), "goal_name": ("string", "for delayed_purchase")}),
    "alerts": (alerts, "Current alerts for the user's finances.", {}),
})
# superseded for the language model by richer versions above (the model sees one tool per job); kept for the calculator
# fallback that answers when the local model is not running
HIDDEN_FROM_LLM = {"spending_forecast", "unusual_transactions", "peer_comparison"}
REQUIRED = {"affordability": ["price"], "emi_calculator": ["principal"], "plan_what_if": ["kind"]}


# ================================================================ Phase 7 remediation tools
TX_FIELDS = ["date", "merchant", "raw_description", "category", "amount", "type", "account_id", "card_id"]   # never internal/label columns


def transactions(ctx, period: str | None = None, category: str | None = None, merchant: str | None = None,
                 sort: str = "amount_desc", limit: int = 5, kind: str = "spending", **_):
    """Individual transactions (not merchant totals), filtered and sorted. kind: spending (debits that are spending) | all."""
    t = _tx(ctx)
    avail = sorted(t["month"].unique().tolist()) if len(t) else []
    try:
        months, desc = _period_months(period, avail)
    except ValueError as e:
        return {"error": str(e), "periods": PERIODS}
    out = {"period": desc, "months": months, "data_covers": f"{avail[0]} to {avail[-1]}" if avail else "no transactions recorded"}
    if not len(t):
        return {**out, "items": [], "count": 0}
    s = t[t["month"].isin(months) & (t["type"] == "debit")]
    if kind != "all":
        s = s[~s["category"].isin(_NON_EXPENSE)]
    if category and str(category).strip().lower() not in ("all", "any", "total", "everything", "none", "*"):
        cat = _std_cat(category)
        if cat in _ALL_CATS or cat == "Uncategorised":
            s = s[s["category"] == cat]
            out["category"] = cat
        else:
            merchant = merchant or str(category)
            out["note_category"] = f"'{category}' is not a Finora category; merchants and descriptions were searched instead."
    if merchant:
        words = [w for w in re.split(r"[^A-Z0-9]+", str(merchant).upper()) if len(w) >= 3]
        text_ = s["merchant"].fillna("").str.upper() + " " + s["raw_description"].fillna("").str.upper()
        hit = _pd.Series(False, index=s.index)
        for w in words or [str(merchant).upper()]:
            hit |= text_.str.contains(w.rstrip("S"), regex=False)
        s = s[hit]
        out["merchant"] = merchant
    limit = max(1, min(int(limit or 5), 20))
    s = s.sort_values("amount", ascending=(sort == "amount_asc")) if sort in ("amount_desc", "amount_asc") else s.sort_values("date", ascending=False)
    acc = {a["id"]: f"{a.get('bank_name')} {a.get('account_masked')}" for a in ctx["identity"].accounts}
    cards = {c["id"]: f"{c.get('issuer')} {c.get('card_name')} ••{c.get('last4')}" for c in ctx["identity"].cards}
    items = []
    for _, r in s.head(limit).iterrows():
        src = cards.get(r.get("card_id")) if _pd.notna(r.get("card_id")) else acc.get(r.get("account_id"))
        items.append({"date": r["date"].date().isoformat(), "merchant": r.get("merchant") or r.get("raw_description"),
                      "category": r["category"], "amount": round(float(r["amount"]), 2), "source": src})
    out.update({"sort": sort, "limit": limit, "items": items, "count_matching": int(len(s)),
                "total_matching": round(float(s["amount"].sum()), 2), "currency": "INR"})
    return out


def health_score(ctx, **_):
    h = ctx["analysis"]["health_score"]
    return {"score": h.get("score"), "band": h.get("band"), "pillars": h.get("pillars"), "not_assessed": h.get("not_assessed"),
            "note": "Finora's overall measure is the Financial Health Score (0-100, six pillars). There is no separate "
                    "'financial discipline score'; savings rate, missed SIPs and on-time card payments show discipline."}


def model_info(ctx, model: str | None = None, **_):
    """Model Lab facts (version, status, data, metrics, baseline, limitations) for one model or all. Read from the registry."""
    from ..ml import registry
    lab = registry.lab()
    alias = {"credit": "credit_risk", "credit risk": "credit_risk", "categoriser": "categoriser", "categorisation": "categoriser",
             "anomaly": "anomaly", "scanner": "anomaly", "forecast": "forecast", "peers": "peers", "peer": "peers"}
    want = alias.get(str(model or "").strip().lower(), model)
    out = []
    for m in lab["models"]:
        if want and m["name"] != want:
            continue
        p, met = m.get("provenance") or {}, m.get("metrics") or {}
        out.append({"model": m["name"], "status": m["status_text"], "version": m.get("version"),
                    "datasets": [d.get("name") for d in p.get("datasets", [])], "label": m.get("label"),
                    "acceptance": [{"criterion": c["criterion"], "passed": c["passed"], "value": c["value"]}
                                   for c in ((m.get("acceptance") or {}).get("checks") or [])],
                    "limitations": p.get("limitations") or met.get("limitations"), "policy": m.get("deployment_policy")})
    return {"models": out} if out else {"error": f"unknown model '{model}'", "models_available": [m["name"] for m in lab["models"]]}


REGISTRY.update({
    "transactions": (transactions, "Individual transactions (NOT merchant totals) for a period, optionally a category or merchant, "
                                   "sorted by amount (largest first) or date: use for 'largest', 'biggest single', 'top N', 'list'.",
                     {"period": ("string", "this_month, last_month, last_3_months, last_6_months, last_12_months, all, or YYYY-MM"),
                      "category": ("string", "optional category"), "merchant": ("string", "optional merchant"),
                      "sort": ("string", "amount_desc (default), amount_asc or date_desc"), "limit": ("integer", "how many, 1-20")}),
    "health_score": (health_score, "The Financial Health Score (0-100) and its six pillars.", {}),
    "model_info": (model_info, "Model Lab facts about Finora's models: version, status, data, acceptance checks, limitations.",
                   {"model": ("string", "credit_risk, categoriser, anomaly, forecast or peers (omit for all)")}),
})

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
            "first_to_clear": plan["avalanche"]["payoff_order"][0]["debt"] if plan["avalanche"]["payoff_order"] else None}


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
    "runway": (runway, "How long savings last if income stops; emergency fund status.", {}),
    "fire_forecast": (fire_forecast, "Financial independence / retirement projection, optionally with what-if changes.",
                      {"monthly_investment": ("number", "What-if monthly investment in rupees"),
                       "retirement_age": ("integer", "What-if target retirement age"),
                       "annual_expenses": ("number", "What-if annual expenses in retirement"),
                       "nominal_return_pct": ("number", "What-if expected annual return in percent")}),
    "affordability": (affordability, "Whether a purchase is affordable, with EMI and impact on finances.",
                      {"price": ("number", "Price in rupees"), "down_payment": ("number", "Down payment in rupees"),
                       "interest_rate": ("number", "Loan interest rate percent"), "tenure_months": ("integer", "Loan tenure in months"),
                       "item_type": ("string", "car, bike, home, phone, gadget, trip, education, wedding or other"),
                       "item_name": ("string", "Name of the item")}),
    "emi_calculator": (emi_calculator, "EMI for any loan amount, rate and tenure.",
                       {"principal": ("number", "Loan amount in rupees"), "interest_rate": ("number", "Annual rate percent"),
                        "tenure_months": ("integer", "Tenure in months")}),
    "tax_comparison": (tax_comparison, "Old vs new income-tax regime for FY 2026-27.",
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
        out.append({"type": "function", "function": {"name": name, "description": desc, "parameters": {
            "type": "object", "properties": {k: {"type": t, "description": d} for k, (t, d) in params.items()},
            "required": ["price"] if name == "affordability" else ["principal"] if name == "emi_calculator" else []}}})
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

"""Rule-based answer writer.

Produces a clear answer from tool results WITHOUT a language model. It is used
(a) when Ollama is not running, and (b) whenever the model's answer fails number verification.
"""
from __future__ import annotations

from ..services.recommendations import _inr as inr

DISCLAIMER = "Educational guidance, not a substitute for a licensed financial advisor."

GLOSSARY = {
    "fire": "FIRE means Financial Independence, Retire Early: building a corpus large enough that its returns cover your living costs. "
            "FIRE number = annual expenses ÷ safe withdrawal rate. Lean FIRE covers a minimal lifestyle, Fat FIRE a richer one, "
            "and Coast FIRE is the point where your existing corpus will grow to the FIRE number without new investments.",
    "sip": "A SIP (Systematic Investment Plan) invests a fixed amount in a mutual fund every month. It averages your purchase price "
           "over time and builds the habit of investing before spending.",
    "emi": "An EMI (Equated Monthly Instalment) is the fixed monthly loan payment. Early EMIs are mostly interest; the principal share grows over time.",
    "runway": "Runway is how many months your liquid savings would cover your expenses if your income stopped today.",
    "credit utilisation": "Credit utilisation is the share of your card limit you are using. Staying under 30% is considered healthy for credit scores.",
    "net worth": "Net worth is everything you own (assets) minus everything you owe (liabilities).",
    "avalanche": "The avalanche method pays the highest-interest debt first (cheapest overall). The snowball method pays the smallest balance first (quick wins).",
    "old regime": "The old tax regime has higher rates but allows deductions (80C, 80D, HRA, home-loan interest). The new regime has lower rates and a bigger "
                  "standard deduction but almost no deductions.",
    "emergency fund": "An emergency fund is 6 months of expenses kept in safe, quickly accessible places such as a savings account, sweep FD or liquid fund.",
    "term insurance": "Term insurance is pure life cover: a low premium for a large payout to your family if you die during the term. Rule of thumb: 10× annual income plus loans.",
    "xirr": "XIRR is the annualised return on investments made at different dates, such as SIP instalments.",
    "mutual fund": "A mutual fund pools money from many investors and invests it in stocks, bonds or both, managed by a fund house.",
    "index fund": "An index fund simply copies a market index such as the Nifty 50, giving diversified equity exposure at very low cost.",
    "inflation": "Inflation is the yearly rise in prices. Money that grows slower than inflation loses purchasing power.",
}


def glossary_answer(question: str) -> str | None:
    q = question.lower()
    for k, v in GLOSSARY.items():
        if k in q and any(w in q for w in ("what is", "what's", "what are", "explain", "meaning", "mean", "define", "how does", "difference")):
            return v
    return None


def _w_profile(f):
    return (f"Your net worth is {inr(f['net_worth'])} (assets {inr(f['total_assets'])}, liabilities {inr(f['total_liabilities'])}). "
            f"You earn about {inr(f['avg_monthly_income'])} and spend {inr(f['avg_monthly_expenses'])} a month, a savings rate of {f['savings_rate_pct']}%. "
            f"Your financial health score is {f['health_score']}/100 ({f['health_band']}). "
            f"Weakest area: {min(f['health_pillars'], key=f['health_pillars'].get)}; strongest: {max(f['health_pillars'], key=f['health_pillars'].get)}.")


def _w_cash(f):
    tops = ", ".join(f"{c['category']} {inr(c['monthly_avg'])}" for c in f["top_categories"][:4])
    return (f"On average you earn {inr(f['avg_monthly_income'])} and spend {inr(f['avg_monthly_expenses'])} a month, saving {inr(f['avg_monthly_savings'])} "
            f"({f['avg_savings_rate_pct']}%). Essentials take {f['essential_to_income_pct']}% of income and discretionary spending {f['discretionary_to_income_pct']}%. "
            f"Biggest categories per month: {tops}. You ended {f['months_in_deficit']} month(s) in deficit.")


def _w_spend(f):
    if "category" in f:
        s = f"You spend about {inr(f['monthly_avg'])} a month on {f['category']} ({f['share_of_spend_pct']}% of your spending)."
        if f.get("last_3m_avg") is not None:
            s += f" The last 3 months averaged {inr(f['last_3m_avg'])}; a sensible limit is {inr(f['suggested_limit'])}."
        return s
    tops = ", ".join(f"{c['category']} {inr(c['monthly_avg'])}" for c in f["categories"][:5])
    sc = f["budget_scenarios"][1]
    return (f"Your biggest monthly spends are: {tops}. Cutting discretionary spending by {sc['cut_discretionary_pct']}% would save "
            f"{inr(sc['monthly_saving'])} a month ({inr(sc['annual_saving'])} a year) and lift your savings rate to {sc['new_savings_rate_pct']}%.")


def _w_networth(f):
    top = sorted(f["breakdown"].items(), key=lambda kv: -kv[1])[:4]
    return (f"Your net worth is {inr(f['net_worth'])}: assets of {inr(f['total_assets'])} minus liabilities of {inr(f['total_liabilities'])}. "
            f"Largest assets: {', '.join(f'{k} {inr(v)}' for k, v in top)}."
            + (f" It changed by {inr(f['change_over_period'])} over the last year." if f.get("change_over_period") is not None else ""))


def _w_invest(f):
    s = (f"Your investments are worth {inr(f['current_value'])} against {inr(f['total_invested'])} invested, a gain of {inr(f['total_gain'])} "
         f"({f['total_gain_pct']}%). You invest {inr(f['sip_monthly_total'])} a month through SIPs ({f['sip_to_income_pct'] or 0}% of income).")
    if f.get("top_sector") and (f["top_sector"]["share_of_stocks_pct"] or 0) >= 50:
        s += f" {f['top_sector']['share_of_stocks_pct']}% of your stocks are in {f['top_sector']['sector']}, which is concentrated."
    if f.get("sips_missed_last_12m"):
        s += f" {f['sips_missed_last_12m']} SIP instalments were missed in the last 12 months."
    if f.get("losing_positions"):
        s += f" Positions at a loss: {', '.join(f['losing_positions'][:4])}."
    return s


def _w_cards(f):
    if not f.get("has_cards", True):
        return "You have no credit cards on file."
    s = (f"Across your cards you owe {inr(f['total_outstanding'])} on a total limit of {inr(f['total_limit'])}: {f['overall_utilisation_pct']}% utilisation "
         f"(under 30% is healthy). Revolving balances cost you about {inr(f['est_interest_per_month'])} a month in interest.")
    worst = max(f["cards"], key=lambda c: c["utilisation_pct"] or 0)
    s += f" Highest: {worst['card']} at {worst['utilisation_pct']}%."
    late = [c for c in f["cards"] if c["months_delayed_last6"]]
    if late:
        s += f" Overdue payments on: {', '.join(c['card'] for c in late)}."
    if f.get("default_risk_pct") is not None:
        s += f" The credit-risk model puts your chance of missing next month's payment at {f['default_risk_pct']}% ({f['default_risk_band']})."
    return s


def _w_debt(f):
    if not f.get("has_debt", True):
        return "You have no outstanding debt."
    s = (f"You owe {inr(f['total_debt'])} in total at an average rate of {f['weighted_avg_rate_pct']}%. EMIs are {inr(f['total_emi'])} a month, "
         f"{f['emi_to_income_pct']}% of income ({f['risk_band']}). ")
    s += (f"Paying the highest-rate debt first (avalanche) makes you debt-free in {f['avalanche_months']} months with {inr(f['avalanche_interest'])} interest, "
          f"versus {inr(f['snowball_interest'])} with smallest-balance-first - a saving of {inr(f['interest_saved_by_avalanche'])}. "
          f"Start with {f['highest_rate_debt']}.")
    if f["extra_monthly_payment"]:
        s += f" This assumes an extra {inr(f['extra_monthly_payment'])} a month."
    return s


def _w_runway(f):
    return (f"If your income stopped today, your liquid savings of {inr(f['emergency_pool'])} would last about {f['runway_months']} months at your current "
            f"spending of {inr(f['avg_monthly_expenses'])} a month ({f['runway_months_essentials_only']} months if you cut to essentials). "
            + ("That meets the 6-month target." if (f["runway_months"] or 0) >= 6 else f"The 6-month target needs {inr(f['emergency_fund_gap'])} more."))


def _w_fire(f):
    i = f["inputs"]
    s = (f"Your FIRE number is {inr(f['fire_number'])} (annual expenses of {inr(i['annual_expenses'])} at a {i['withdrawal_rate_pct']}% withdrawal rate). "
         f"You have {inr(i['current_corpus'])} invested ({f['progress_pct']}% of the way) and invest {inr(i['monthly_investment'])} a month. ")
    s += (f"At this pace you reach financial independence at age {f['fire_age']}. " if f["fire_age"] else
          "At this pace you do not reach financial independence before age 75. ")
    if f.get("retirement_age_target"):
        s += (f"For your target of {f['retirement_age_target']}, the projected corpus is {inr(f['corpus_at_target_age'])}"
              + (" - on track" if f["on_track"] else f", a shortfall of {inr(f['shortfall_at_target_age'])}")
              + f"; success probability {f['success_probability_pct']}%. ")
        if not f["on_track"] and f.get("monthly_investment_needed_for_target"):
            s += f"You would need to invest about {inr(f['monthly_investment_needed_for_target'])} a month to hit it. "
    alt = f.get("if_you_invested_80pct_of_surplus")
    if alt and alt["monthly_investment"] > i["monthly_investment"] * 1.2:
        s += f"Investing {inr(alt['monthly_investment'])} a month (80% of your surplus) would change your FIRE age to {alt['fire_age'] or 'beyond 75'}. "
    return s + "All figures are in today's rupees."


def _w_afford(f):
    imp = f["impact"]
    s = (f"Verdict: {f['verdict']}. For {f['item']} at {inr(f['price'])} with {inr(f['down_payment'])} down, the loan is {inr(f['loan_amount'])} at "
         f"{f['interest_rate_pct']}% for {f['tenure_months']} months: EMI {inr(f['emi'])}, total interest {inr(f['total_interest'])}. ")
    s += (f"Your EMIs would go from {imp['emi_to_income_pct']['before']}% to {imp['emi_to_income_pct']['after']}% of income, monthly surplus from "
          f"{inr(imp['monthly_surplus']['before'])} to {inr(imp['monthly_surplus']['after'])}, and runway from {imp['runway_months']['before']} to "
          f"{imp['runway_months']['after']} months. ")
    if imp.get("fire_delay_years"):
        s += f"Financial independence would be delayed by {imp['fire_delay_years']} years. "
    s += "Why: " + " ".join(f["reasons"][:3]) + " "
    if f["verdict"] != "AFFORDABLE":
        if f.get("best_option") and f["best_option"] != "Your plan":
            s += f"Better option: {f['best_option']}. "
        if f.get("max_affordable_price_same_terms"):
            s += f"On the same terms, about {inr(f['max_affordable_price_same_terms'])} would be comfortably affordable."
    assumed = [k.replace('_', ' ') for k, v in f["assumed_defaults"].items() if v]
    if assumed:
        s += f" (Assumed typical {', '.join(assumed)} - tell me yours for an exact answer.)"
    return s


def _w_emi(f):
    return (f"A loan of {inr(f['principal'])} at {f['interest_rate_pct']}% for {f['tenure_months']} months has an EMI of {inr(f['emi'])}. "
            f"You would pay {inr(f['total_interest'])} in interest, {inr(f['total_payment'])} in total.")


def _w_tax(f):
    return (f"For FY {f['financial_year']} on income of {inr(f['gross_income'])}: new regime tax is {inr(f['new_regime_tax'])}, old regime "
            f"{inr(f['old_regime_tax'])} (using {inr(f['old_regime_deductions_used'])} of deductions). The {f['better_regime']} regime saves you "
            f"{inr(f['saving_with_better'])}. The old regime only wins if your deductions exceed about {inr(f['old_regime_breakeven_deductions'])}. "
            "This is an estimate, not tax-filing advice.")


def _w_forecast(f):
    if not f.get("available", True):
        return "There is not enough history to forecast next month yet."
    s = (f"For {f['prediction_month']} the model predicts spending of {inr(f['predicted_total_expense'])} (likely range {inr(f['range']['low'])}"
         f"-{inr(f['range']['high'])}), {f['change_vs_last_month_pct']:+}% versus last month. With expected income of {inr(f['expected_income'])} "
         f"that is a projected {f['projected_status']} of {inr(abs(f['projected_surplus']))}.")
    if f.get("top_increase_drivers"):
        s += f" Categories pushing it up: {', '.join(f['top_increase_drivers'])}."
    return s


def _w_anomaly(f):
    if not f["flagged_count"]:
        return "No unusual transactions were flagged."
    items = "; ".join(f"{t['date']} {t['merchant'] or t['category']} {inr(t['amount'])} ({t['times_typical']}× your typical) on {t['source']}"
                      for t in f["transactions"][:4])
    return (f"{f['flagged_count']} transactions were flagged as unusual, totalling {inr(f['flagged_amount_total'])}. Most notable: {items}. "
            "Unusual does not mean fraudulent - just check that you recognise them.")


def _w_recs(f):
    lines = [f"{n}. {r['finding']} - {r['action']}" for n, r in enumerate(f["recommendations"][:4], 1)]
    return "Your top priorities:\n" + "\n".join(lines)


def _w_ins(f):
    s = f"Health cover: {inr(f['health_cover'])} (recommended at least {inr(f['recommended_health_cover'])}). Term life cover: {inr(f['term_cover'])} (guideline {inr(f['recommended_term_cover'])})."
    gaps = [x for x in (f"health gap {inr(f['health_gap'])}" if f["health_gap"] else "", f"term gap {inr(f['term_gap'])}" if f["term_gap"] else "") if x]
    return s + (" Gaps: " + ", ".join(gaps) + "." if gaps else " You are adequately covered.")


def _w_goals(f):
    if not f["goals"]:
        return "You have no goals set up yet."
    return " ".join(f"{g['name']}: {g['progress_pct']}% of {inr(g['target'])}, needs about {inr(g['monthly_needed_at_7pct'])} a month for {g['months_left']} months."
                    for g in f["goals"])


def _w_peers(f):
    return (f"You are closest to the '{f['peer_group']}' group. Strengths versus others: {', '.join(f['strengths']) or 'none stand out'}. "
            f"Weaker than most on: {', '.join(f['weaknesses']) or 'nothing notable'}.")


WRITERS = {"profile_summary": _w_profile, "cash_flow": _w_cash, "spending_by_category": _w_spend, "net_worth": _w_networth,
           "investments": _w_invest, "credit_cards": _w_cards, "debts_and_payoff": _w_debt, "runway": _w_runway,
           "fire_forecast": _w_fire, "affordability": _w_afford, "emi_calculator": _w_emi, "tax_comparison": _w_tax,
           "spending_forecast": _w_forecast, "unusual_transactions": _w_anomaly, "recommendations": _w_recs,
           "insurance": _w_ins, "goals": _w_goals, "peer_comparison": _w_peers}


def write(results: list[tuple[str, dict]]) -> str:
    parts = []
    for name, facts in results:
        if "error" in facts:
            continue
        try:
            parts.append(WRITERS[name](facts))
        except Exception:
            continue
    return "\n\n".join(parts) if parts else "I could not compute that from your data."

"""Recommendation engine + alerts.

Deterministic rules that combine model findings with financial calculations.
A rule only fires when every number it relies on is actually known for this person: missing data never
counts as zero (an unknown savings rate is not a 0% savings rate).
Every recommendation carries: finding, evidence (the actual numbers), explanation,
action, priority and - only when it can be calculated - the rupee impact.
The AI assistant may re-word these, but it never invents them.
"""
from __future__ import annotations


def _inr(x) -> str:
    x = float(x or 0)
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build(snap: dict, ml: dict) -> list[dict]:
    cf, liq, cred, debt = snap["cash_flow"], snap["liquidity"], snap["credit"], snap["debt"]
    ins, inv, idle, bud, fire, alloc = snap["insurance"], snap["investments"], snap["idle_money"], snap["budget"], snap["fire"], snap["allocation"]
    recs: list[dict] = []

    def add(code, priority, finding, evidence, explanation, action, impact_inr=None, impact_text=None, source="Financial calculations"):
        recs.append(dict(code=code, priority=priority, finding=finding, evidence=evidence, explanation=explanation,
                         action=action, impact_inr=None if impact_inr is None else round(float(impact_inr)),
                         impact_text=impact_text, source=source))

    sr_known = cf["avg_savings_rate_pct"] is not None
    # ---- 1. overspending
    if sr_known and cf["avg_savings_rate_pct"] < 0:
        gap = -cf["avg_monthly_savings"]
        add("DEFICIT", "high", "You spend more than you earn",
            f"Average income {_inr(cf['avg_monthly_income'])}/month vs expenses {_inr(cf['avg_monthly_expenses'])}/month; "
            f"{cf['months_in_deficit']} of {cf['period']['months']} months ended in deficit.",
            "A persistent deficit is being funded by credit cards or savings, which compounds quickly.",
            f"Cut discretionary spending by at least {_inr(gap)} a month. A 30% cut frees {_inr(bud['scenarios'][2]['monthly_saving'])}/month.",
            gap * 12, f"Closing the gap stops about {_inr(gap * 12)} of new debt a year.")
    elif sr_known and cf["avg_savings_rate_pct"] < 20 and bud.get("scenarios"):
        s = bud["scenarios"][1]
        add("LOW_SAVINGS", "medium", "Savings rate is below the 20% guideline",
            f"You save {cf['avg_savings_rate_pct']}% of income ({_inr(cf['avg_monthly_savings'])}/month).",
            "Saving 20%+ of income is the usual base for building wealth and reaching goals.",
            f"Trim discretionary spending by 20% to lift your savings rate to {s['new_savings_rate_pct']}%.",
            s["annual_saving"], f"{_inr(s['annual_saving'])} more saved per year.")

    # ---- 2. credit cards
    if cred.get("has_cards"):
        for c in cred["cards"]:
            if (c["months_delayed_last6"] or 0) > 0:
                add(f"CARD_LATE_{c['last4']}", "high", f"Payments on {c['card']} are overdue",
                    f"{c['months_delayed_last6']} delayed payment(s) in the last 6 months; outstanding {_inr(c['outstanding'])}; minimum due {_inr(c['min_due'])}.",
                    "Late payments add late fees and interest and are the strongest negative signal for a credit score.",
                    f"Pay at least the minimum due of {_inr(c['min_due'])} immediately and set up auto-pay for the minimum.",
                    c["est_interest_per_month"] * 12, f"Avoids roughly {_inr(c['est_interest_per_month'] * 12)} a year in interest plus late fees.",
                    "Credit analysis + credit-risk model")
            elif c["utilisation_pct"] is not None and c["utilisation_pct"] >= 50:
                add(f"CARD_UTIL_{c['last4']}", "high" if c["utilisation_pct"] >= 75 else "medium",
                    f"{c['card']} is {c['utilisation_pct']:.0f}% utilised",
                    f"Outstanding {_inr(c['outstanding'])} on a limit of {_inr(c['limit'])}"
                    + (f"; only part of the bill was paid in {c['months_paid_minimum_only_last6']} of the last 6 months."
                       if c["months_paid_minimum_only_last6"] is not None else "."),
                    "Utilisation above 30% lowers credit scores, and revolving balances are charged about "
                    f"{c['apr_pct']:.0f}% a year.",
                    f"Bring the balance under {_inr(c['limit'] * 0.3)} (30% of the limit); pay more than the minimum every month.",
                    c["est_interest_per_month"] * 12, f"Currently costing about {_inr(c['est_interest_per_month'])} a month in interest.")
    risk = ml.get("credit_risk") or {}
    if risk.get("has_cards") and risk.get("overall_risk_band") in {"high", "very high"}:
        top = risk["cards"][0]["top_factors"][:2] if risk.get("cards") else []
        worst = max(risk["cards"], key=lambda c: c["default_probability_pct"])
        add("DEFAULT_RISK", "high", "High risk of missing a card payment next month",
            f"Model estimate: {risk['overall_default_probability_pct']}% (population average {risk['population_base_rate_pct']}%), driven by {worst['card']}. "
            f"Main factors: {', '.join(f['factor'] for f in worst['top_factors'][:3])}.",
            "The credit-risk model, trained on 30,000 real card accounts, sees a payment pattern that often precedes default.",
            "Prioritise clearing overdue amounts, then pay the full statement balance for the next three months.",
            None, None, "Credit-risk model (XGBoost)")

    # ---- 3. costly debt vs idle money
    costly = [d for d in idle["high_interest_debts"] if d["rate"] >= 12]
    idle_amt = idle["idle_in_low_yield_accounts"] if idle.get("available", True) else None
    if idle_amt is not None and idle_amt > 10000 and costly:
        d = max(costly, key=lambda x: x["rate"])
        pay = min(idle["idle_in_low_yield_accounts"], d["balance"])
        add("IDLE_VS_DEBT", "high", "Idle savings while paying high-interest debt",
            f"{_inr(idle['idle_in_low_yield_accounts'])} sits in accounts earning under 4%, while {d['name']} costs {d['rate']}% on {_inr(d['balance'])}.",
            "Money earning 3% while debt costs far more is a guaranteed loss on the difference.",
            f"Use {_inr(pay)} of the idle balance to prepay {d['name']} (keeping 1.5 months of expenses as a buffer).",
            pay * (d["rate"] - 3) / 100, f"Saves about {_inr(pay * (d['rate'] - 3) / 100)} a year.")
    elif idle_amt is not None and idle_amt > 50000:
        add("IDLE_CASH", "low", "Surplus cash is sitting in a low-interest account",
            f"{_inr(idle['idle_in_low_yield_accounts'])} above your operating buffer earns under 4%.",
            "After inflation, money in a savings account loses purchasing power.",
            "Move the surplus to a liquid/short-term debt fund or a sweep-in FD, or add it to your SIPs.",
            idle["annual_opportunity_cost"], f"About {_inr(idle['annual_opportunity_cost'])} more a year at ~7%.")

    # ---- 4. debt load
    if debt["has_debt"] and (debt["emi_to_income_pct"] or 0) >= 35:
        add("HIGH_EMI", "high" if debt["emi_to_income_pct"] >= 50 else "medium", f"EMIs take {debt['emi_to_income_pct']:.0f}% of your income",
            f"Total EMIs {_inr(debt['total_emi'])}/month on {len(debt['loans'])} loans; total debt {_inr(debt['total_debt'])}.",
            "Lenders treat 40% as the comfortable ceiling. Above it, one bad month can cause a missed payment.",
            f"Do not take new loans; direct any bonus to {debt['highest_rate_debt']} (your costliest debt).")
    if debt["has_debt"] and debt.get("payoff") and debt["payoff"]["interest_saved_by_avalanche"] > 1000:
        add("PAYOFF_ORDER", "medium", "Pay debts in order of interest rate",
            f"Paying highest-rate first ('avalanche') costs {_inr(debt['payoff']['avalanche']['total_interest'])} in interest vs "
            f"{_inr(debt['payoff']['snowball']['total_interest'])} for smallest-balance first.",
            "Clearing the highest-rate debt first minimises total interest.",
            f"Send every extra rupee to {debt['highest_rate_debt']} first, while paying minimums on the rest.",
            debt["payoff"]["interest_saved_by_avalanche"], f"Saves {_inr(debt['payoff']['interest_saved_by_avalanche'])} in interest.")

    # ---- 5. emergency fund
    ef = liq["emergency_fund_months"]
    if ef is None:
        pass  # expenses unknown: the emergency fund cannot be judged (see data completeness)
    elif ef < 3:
        add("EMERGENCY_FUND", "high", f"Emergency fund covers only {ef:.1f} months",
            f"Liquid savings {_inr(liq['emergency_pool'])} vs average expenses {_inr(cf['avg_monthly_expenses'])}/month. Target: 6 months ({_inr(6 * cf['avg_monthly_expenses'])}).",
            "Without a cushion, a job loss or medical bill has to go on a credit card or loan.",
            f"Build the fund before increasing investments: set aside {_inr(liq['emergency_fund_gap'] / 12)} a month for 12 months in a liquid fund or sweep FD.",
            None, f"Gap to target: {_inr(liq['emergency_fund_gap'])}.")
    elif ef < 6:
        add("EMERGENCY_FUND", "medium", f"Emergency fund is {ef:.1f} months - short of the 6-month target",
            f"Liquid savings {_inr(liq['emergency_pool'])}; gap {_inr(liq['emergency_fund_gap'])}.",
            "Six months of expenses is the standard cushion, more for variable income.",
            f"Top up by {_inr(liq['emergency_fund_gap'] / 12)} a month over the next year.")

    # ---- 6. protection
    if not ins["has_health"] or ins["health_gap"] > 0:
        add("HEALTH_COVER", "high" if not ins["has_health"] else "medium",
            "No personal health insurance" if not ins["has_health"] else "Health cover is below ₹10 lakh",
            f"Current cover {_inr(ins['health_cover'])}; recommended at least {_inr(ins['recommended_health_cover'])}.",
            "A single hospitalisation can wipe out years of savings; employer cover ends when the job does.",
            "Buy a personal/family floater health policy of ₹10 lakh or more.")
    if ins["dependants_likely"] and ins["term_gap"] is not None and ins["term_gap"] > 0:
        add("TERM_COVER", "high" if not ins["has_term"] else "medium",
            "No term life insurance" if not ins["has_term"] else "Term cover is lower than recommended",
            f"Current cover {_inr(ins['term_cover'])}; guideline (10× income + loans) {_inr(ins['recommended_term_cover'])}.",
            "Term insurance protects dependants and repays loans if your income stops.",
            f"Add pure term cover of about {_inr(ins['term_gap'])}.")

    # ---- 7. investing
    if inv["sips_missed_last_12m"] >= 2:
        add("SIP_DISCIPLINE", "medium", f"{inv['sips_missed_last_12m']} SIP instalments were missed or stopped in the last 12 months",
            "; ".join(f"{s['scheme']}: {s['status']}, {s['missed_last_12m']} missed" for s in inv["sips"] if s["missed_last_12m"]),
            "Skipped instalments break compounding and usually happen when cash flow is tight.",
            "Move the SIP date to 2-3 days after your income arrives, and restart paused SIPs at an amount you can sustain.")
    if inv["sip_to_income_pct"] is not None and inv["sip_to_income_pct"] < 10 and sr_known and cf["avg_savings_rate_pct"] >= 15:
        extra = max(0.0, cf["avg_monthly_savings"] * 0.6 - inv["sip_monthly_total"])
        alt = fire.get("if_you_invested_80pct_of_surplus", {})
        add("INVEST_SURPLUS", "medium", "You save well but invest little of it",
            f"Monthly surplus {_inr(cf['avg_monthly_savings'])}, but only {_inr(inv['sip_monthly_total'])} goes into SIPs ({inv['sip_to_income_pct'] or 0}% of income).",
            "Savings left in a bank account do not beat inflation; investing the surplus is what brings financial independence closer.",
            f"Start or increase SIPs by about {_inr(extra)} a month.",
            None, f"Investing 80% of your surplus would move your FIRE age from {fire['fire_age'] or 'beyond 75'} to {alt.get('fire_age') or 'beyond 75'}."
            if alt else None, "FIRE engine")
    if inv["top_sector"] and inv["stock_count"] >= 3 and (inv["top_sector"]["share_of_stocks_pct"] or 0) >= 50:
        add("CONCENTRATION", "medium", f"{inv['top_sector']['share_of_stocks_pct']:.0f}% of your stocks are in one sector",
            f"Sector: {inv['top_sector']['sector']}. Positions currently at a loss: {', '.join(inv['losing_positions'][:4]) or 'none'}.",
            "A concentrated portfolio rises and falls with one industry.",
            "Shift new money into a diversified index or flexi-cap fund instead of adding more single stocks in this sector.")
    if alloc["equity_gap_pct"] is not None and alloc["equity_gap_pct"] < -25 and (cf["avg_savings_rate_pct"] or 0) > 0:
        add("LOW_EQUITY", "low", "Equity share is low for your age",
            f"Equity is {alloc['financial_assets_equity_pct']}% of your financial assets; the age-based guide suggests about {alloc['suggested_equity_pct_for_age']}%.",
            "Over long periods equity has out-grown fixed-income; too little of it slows wealth creation.",
            "Raise equity gradually through monthly SIPs in an index fund rather than a lump sum.")

    # ---- 8. anomalies
    an = ml.get("anomaly") or {}
    serious = [f for f in an.get("flagged", []) if f["severity"] in {"high", "medium"}]
    if serious:
        top = serious[0]
        add("VERIFY_TXN", "high" if any(f["severity"] == "high" for f in serious) else "medium",
            f"{len(serious)} unusual transaction(s) need a quick check",
            "; ".join(f"{f['date']} {f['merchant'] or f['category']} {_inr(f['amount'])} ({f['times_typical']}× typical) via {f['source']}" for f in serious[:3]),
            "These amounts are far outside your normal pattern. Unusual is not the same as fraudulent.",
            "Confirm you made these payments; if any is unfamiliar, contact the bank/card issuer and block the card.",
            sum(f["amount"] for f in serious), f"{_inr(sum(f['amount'] for f in serious))} of spending to verify.", "Anomaly detector (Isolation Forest)")

    # ---- 9. forecast
    fc = ml.get("forecast") or {}
    if fc.get("available"):
        if fc["projected_status"] == "deficit":
            add("FORECAST_DEFICIT", "high", f"Next month ({fc['prediction_month']}) is forecast to end in deficit",
                f"Predicted spend {_inr(fc['predicted_total_expense'])} (range {_inr(fc['range']['low'])}-{_inr(fc['range']['high'])}) vs expected income {_inr(fc['expected_income'])}.",
                "The forecaster projects spending above income based on your recent pattern.",
                "Hold spending in " + (", ".join(fc["top_increase_drivers"]) or "discretionary categories") + " to the suggested budgets this month.",
                -fc["projected_surplus"], f"Projected shortfall {_inr(-fc['projected_surplus'])}.", "Cash-flow forecaster (XGBoost)")
        rising = [c for c in fc["category_predictions"] if c["trend"] == "rising" and c["predicted"] - c["three_month_avg"] > 1500][:2]
        for c in rising:
            add(f"RISING_{c['category'].upper()}", "low", f"{c['category']} spending is forecast to rise",
                f"Predicted {_inr(c['predicted'])} next month vs a 3-month average of {_inr(c['three_month_avg'])} ({c['change_vs_3m_avg_pct']:+.0f}%).",
                "A rising category is the cheapest place to act before it becomes a habit.",
                f"Set a {c['category']} budget of {_inr(c['suggested_budget'])} for next month.",
                (c["predicted"] - c["suggested_budget"]) * 12, f"About {_inr((c['predicted'] - c['suggested_budget']) * 12)} a year if held.",
                "Cash-flow forecaster (XGBoost)")

    # ---- 10. budget overspend
    for lim in bud["category_limits"][:3]:
        if (lim["overspend_vs_12m_pct"] or 0) >= 20 and lim["last_3m_avg"] - lim["12m_avg"] > 1500:
            add(f"OVERSPEND_{lim['category'].upper()}", "medium", f"{lim['category']} spending has jumped recently",
                f"Last 3 months average {_inr(lim['last_3m_avg'])} vs 12-month average {_inr(lim['12m_avg'])} ({lim['overspend_vs_12m_pct']:+.0f}%).",
                "Recent months are well above your own norm for this category.",
                f"Cap {lim['category']} at {_inr(lim['suggested_limit'])} a month.",
                (lim["last_3m_avg"] - lim["suggested_limit"]) * 12, f"{_inr((lim['last_3m_avg'] - lim['suggested_limit']) * 12)} a year.")

    # ---- 11. FIRE
    if fire.get("available", True) and fire.get("on_track") is False and fire.get("monthly_investment_needed_for_target"):
        need = fire["monthly_investment_needed_for_target"]
        cur = fire["inputs"]["monthly_investment"]
        feasible = cf["avg_monthly_savings"] is not None and need <= max(cf["avg_monthly_savings"], 0)
        add("FIRE_GAP", "medium" if feasible else "low", f"Not on track to retire at {fire['retirement_age_target']}",
            f"FIRE number {_inr(fire['fire_number'])}; projected corpus at {fire['retirement_age_target']}: {_inr(fire['corpus_at_target_age'])}; "
            f"success probability {fire['success_probability_pct']}%. Projected FIRE age: {fire['fire_age'] or 'beyond 75'}.",
            "At the current investing rate the corpus will not support your expenses by the target age.",
            (f"Raise monthly investments from {_inr(cur)} to about {_inr(need)}." if feasible else
             f"Reaching it needs about {_inr(need)}/month, more than your current surplus - consider a later target age or lower expenses."),
            None, f"Shortfall at target age: {_inr(fire['shortfall_at_target_age'])} (today's rupees).", "FIRE engine")

    # ---- 12. tax
    tax = snap["tax"]
    if tax.get("available", True) and tax.get("saving_with_better", 0) > 5000:
        add("TAX_REGIME", "low", f"The {tax['better_regime']} tax regime looks cheaper for you",
            f"Estimated tax: new regime {_inr(tax['new']['total_tax'])} vs old regime {_inr(tax['old']['total_tax'])} (FY {tax['financial_year']}).",
            "The better regime depends on how many deductions you can claim.",
            f"Confirm the {tax['better_regime']} regime with your employer/CA before filing. Old regime breaks even only above {_inr(tax['old_regime_breakeven_deductions'])} of deductions.",
            tax["saving_with_better"], f"Estimated saving {_inr(tax['saving_with_better'])} a year.", "Tax calculator")

    # ---- positive reinforcement when things are healthy
    hs = snap["health_score"]
    if not [r for r in recs if r["priority"] == "high"] and hs["score"] is not None and hs["score"] >= 75 and not hs.get("partial") \
            and sr_known and ef is not None:
        add("ON_TRACK", "low", "Your finances are in good shape",
            f"Health score {snap['health_score']['score']}/100; savings rate {cf['avg_savings_rate_pct']}%; emergency fund {ef:.1f} months.",
            "No urgent issues were found.", "Keep the current plan and review once a quarter.")

    recs.sort(key=lambda r: (PRIORITY_ORDER[r["priority"]], -(r["impact_inr"] or 0)))
    return recs


def alerts(snap: dict, ml: dict, recs: list[dict]) -> list[dict]:
    """Short, time-sensitive notices for the dashboard and the AI CFO."""
    out = []
    for r in recs:
        if r["priority"] == "high":
            out.append({"level": "critical" if r["code"].startswith(("CARD_LATE", "DEFICIT", "DEFAULT_RISK")) else "warning",
                        "title": r["finding"], "detail": r["evidence"], "code": r["code"]})
    fc = ml.get("forecast") or {}
    if fc.get("available") and fc.get("cash_crunch_warning"):
        out.append({"level": "warning", "title": "Bank balance may run low next month",
                    "detail": f"Projected balance at the end of {fc['prediction_month']}: {_inr(fc['projected_bank_balance_end_of_month'])}.",
                    "code": "CASH_CRUNCH"})
    for c in snap["credit"].get("cards", []):
        if c["outstanding"] > 0:
            out.append({"level": "info", "title": f"{c['card']} bill due on day {c['due_day']}",
                        "detail": f"Outstanding {_inr(c['outstanding'])}, minimum due {_inr(c['min_due'])}.", "code": f"DUE_{c['last4']}"})
    return out[:10]

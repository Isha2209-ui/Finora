"""Deterministic financial calculations - plain, auditable formulas (no ML, no LLM).

All money values are INR. Every ratio guards against zero/missing denominators.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ..config import AS_OF_DATE
from ..data.generator import DISCRETIONARY, ESSENTIAL, NON_EXPENSE
from .cleaning import clean_transactions
from .loader import Identity

AS_OF = date.fromisoformat(AS_OF_DATE)


def pct(num, den):
    if den is None or den == 0 or pd.isna(den) or num is None or pd.isna(num):
        return None
    return round(float(num) / float(den) * 100, 2)


def r(x, nd=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


# ================================================================ data coverage
def coverage(ident: Identity) -> dict:
    """What the history can and cannot support. Missing data is reported as missing - never filled with zeros.

    spending_known: at least one transaction exists, so expenses can be measured for those months.
    income_known:   at least one income record exists inside the measured window.
    Cash-flow window: the months that have transactions (expenses are only knowable there); with no
    transactions at all, the months that have income records.
    """
    tx_months = sorted(pd.to_datetime(ident.transactions["date"]).dt.to_period("M").astype(str).unique()) if len(ident.transactions) else []
    inc_months = sorted(pd.to_datetime(ident.income["date"]).dt.to_period("M").astype(str).unique()) if len(ident.income) else []
    window = tx_months or inc_months
    inc_in_window = [m for m in inc_months if m in set(window)]
    return {"spending_known": bool(tx_months), "income_known": bool(inc_in_window), "window": window,
            "months": len(window), "transaction_months": len(tx_months), "income_months": len(inc_months),
            "income_months_in_window": len(inc_in_window)}


# ================================================================ cash flow
def monthly_frame(ident: Identity) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    t, report = clean_transactions(ident.transactions)
    inc = ident.income.copy()
    inc["month"] = pd.to_datetime(inc["date"]).dt.to_period("M").astype(str)
    months = coverage(ident)["window"]
    g = t.groupby("month")
    f = pd.DataFrame(index=months)
    f["income"] = inc.groupby("month")["amount"].sum()
    f["expenses"] = g["spend"].sum()
    f["essential"] = t[t["category"].isin(ESSENTIAL)].groupby("month")["spend"].sum()
    f["discretionary"] = t[t["category"].isin(DISCRETIONARY)].groupby("month")["spend"].sum()
    f["emi"] = t[t["category"] == "EMI"].groupby("month")["spend"].sum()
    f["cash"] = t[t["category"] == "Cash"].groupby("month")["spend"].sum()
    f["invested"] = t[(t["category"] == "Investment") & (t["type"] == "debit")].groupby("month")["amount"].sum()
    f["txn_count"] = t[t["spend"] > 0].groupby("month")["spend"].count()
    f = f.fillna(0.0)
    f["savings"] = f["income"] - f["expenses"]
    f.index.name = "month"
    return f.reset_index(), t, report


_CF_INCOME_FIELDS = ["monthly_income", "avg_monthly_income", "income_volatility_pct"]
_CF_SPEND_FIELDS = ["monthly_expenses", "avg_monthly_expenses", "expense_change", "expense_change_pct", "expense_volatility_pct"]
_CF_BOTH_FIELDS = ["monthly_savings", "savings_rate_pct", "avg_monthly_savings", "avg_savings_rate_pct", "essential_to_income_pct",
                   "discretionary_to_income_pct", "emi_to_income_pct", "invested_to_income_pct", "surplus_or_deficit",
                   "months_in_deficit"]


def cash_flow(ident: Identity) -> dict:
    cov = coverage(ident)
    if not cov["months"]:
        return {"available": False, "income_known": False, "spending_known": False, "coverage": cov,
                "reason": "No income records or transactions yet. Add income and transactions, or upload a statement, "
                          "to measure cash flow.",
                "period": None, "latest_month": None, **{k: None for k in _CF_INCOME_FIELDS + _CF_SPEND_FIELDS + _CF_BOTH_FIELDS},
                "monthly_series": [], "category_totals": [], "spend_by_source": [], "cleaning_report": None}
    out = _cash_flow(ident)
    out.update({"available": True, "income_known": cov["income_known"], "spending_known": cov["spending_known"], "coverage": cov})
    missing = []
    if not cov["income_known"]:
        missing += _CF_INCOME_FIELDS + _CF_BOTH_FIELDS
        out["income_note"] = "No income recorded for these months, so income, savings and income ratios are not calculated."
    if not cov["spending_known"]:
        missing += _CF_SPEND_FIELDS + _CF_BOTH_FIELDS
        out["spending_note"] = "No transactions yet, so spending and savings cannot be measured (not assumed to be zero)."
    for k in set(missing):
        out[k] = None
    if missing:
        out["monthly_series"] = [{**row, **({"income": None} if not cov["income_known"] else {}),
                                  **({"expenses": None, "essential": None, "discretionary": None} if not cov["spending_known"] else {}),
                                  "savings": None} for row in out["monthly_series"]]
    return out


def _cash_flow(ident: Identity) -> dict:
    f, t, report = monthly_frame(ident)
    last, prev = f.iloc[-1], f.iloc[-2] if len(f) > 1 else None
    tot_inc, tot_exp = f["income"].sum(), f["expenses"].sum()
    cat = t[t["spend"] != 0].groupby("category")["spend"].sum().sort_values(ascending=False)
    n = len(f)
    by_source = []
    acct_names = {a["id"]: f"{a['bank_name']} {a['account_type'].title()} {a['account_masked']}" for a in ident.accounts}
    card_names = {c["id"]: f"{c['issuer']} {c['card_name']} ••{c['last4']}" for c in ident.cards}
    spend_rows = t[t["spend"] != 0]
    for aid, s in spend_rows.dropna(subset=["account_id"]).groupby("account_id")["spend"].sum().items():
        by_source.append({"source": acct_names.get(int(aid), str(aid)), "kind": "account", "spend": r(s), "monthly_avg": r(s / n)})
    if "card_id" in spend_rows:
        for cid, s in spend_rows.dropna(subset=["card_id"]).groupby("card_id")["spend"].sum().items():
            by_source.append({"source": card_names.get(int(cid), str(cid)), "kind": "card", "spend": r(s), "monthly_avg": r(s / n)})
    return {
        "period": {"from": f["month"].iloc[0], "to": f["month"].iloc[-1], "months": n},
        "latest_month": last["month"],
        "monthly_income": r(last["income"]), "monthly_expenses": r(last["expenses"]),
        "monthly_savings": r(last["savings"]), "savings_rate_pct": pct(last["savings"], last["income"]),
        "avg_monthly_income": r(f["income"].mean()), "avg_monthly_expenses": r(f["expenses"].mean()),
        "avg_monthly_savings": r(f["savings"].mean()), "avg_savings_rate_pct": pct(tot_inc - tot_exp, tot_inc),
        "essential_to_income_pct": pct(f["essential"].sum(), tot_inc),
        "discretionary_to_income_pct": pct(f["discretionary"].sum(), tot_inc),
        "emi_to_income_pct": pct(f["emi"].sum(), tot_inc),
        "invested_to_income_pct": pct(f["invested"].sum(), tot_inc),
        "surplus_or_deficit": "surplus" if last["savings"] >= 0 else "deficit",
        "months_in_deficit": int((f["savings"] < 0).sum()),
        "expense_change": r(last["expenses"] - prev["expenses"]) if prev is not None else None,
        "expense_change_pct": pct(last["expenses"] - prev["expenses"], prev["expenses"]) if prev is not None else None,
        "income_volatility_pct": pct(f["income"].std(), f["income"].mean()),
        "expense_volatility_pct": pct(f["expenses"].std(), f["expenses"].mean()),
        "monthly_series": [{k: (v if k == "month" else r(v)) for k, v in row.items()} for row in f.to_dict("records")],
        "category_totals": [{"category": c, "total": r(v), "monthly_avg": r(v / n),
                             "share_of_spend_pct": pct(v, cat.sum()),
                             "type": "essential" if c in ESSENTIAL else "discretionary" if c in DISCRETIONARY else "other"}
                            for c, v in cat.items()],
        "spend_by_source": sorted(by_source, key=lambda x: -x["spend"]),
        "cleaning_report": report,
    }


# ================================================================ net worth & allocation
EQUITY_MF = {"equity", "index", "elss"}


def _mf_value(f):
    return f["units"] * f["current_nav"]


def net_worth(ident: Identity) -> dict:
    b = {}
    b["Bank balances"] = sum(a["balance"] for a in ident.accounts)
    b["Cash in hand"] = sum(o["value"] for o in ident.other_assets if o["kind"] == "cash")
    b["Fixed deposits"] = sum(_fd_value(f) for f in ident.fds)
    b["Equity"] = sum(s["quantity"] * s["current_price"] for s in ident.stocks)
    b["Mutual funds"] = sum(_mf_value(f) for f in ident.mfs)
    b["Gold"] = sum(o["value"] for o in ident.other_assets if o["kind"] == "gold")
    b["Retirement (EPF/PPF/NPS)"] = sum(o["value"] for o in ident.other_assets if o["kind"] in {"epf", "ppf", "nps"})
    b["Real estate"] = sum(p["current_value"] for p in ident.properties)
    b["Other"] = sum(o["value"] for o in ident.other_assets if o["kind"] in {"crypto", "bonds"})
    loans = {l["loan_type"] + f" ({l['lender']})": l["balance"] for l in ident.loans}
    cards = {f"{c['issuer']} {c['card_name']} card": c["outstanding"] for c in ident.cards if c["outstanding"] > 0}
    total_assets = sum(b.values())
    total_liab = sum(loans.values()) + sum(cards.values())
    hist = ident.net_worth_history
    change_12m = (hist[-1]["net_worth"] - hist[0]["net_worth"]) if len(hist) > 1 else None
    return {
        "total_assets": r(total_assets), "total_liabilities": r(total_liab), "net_worth": r(total_assets - total_liab),
        "breakdown": {k: r(v) for k, v in b.items() if v},
        "liabilities": {**{k: r(v) for k, v in loans.items()}, **{k: r(v) for k, v in cards.items()}},
        "debt_to_assets_pct": pct(total_liab, total_assets),
        "history": [{"month": h["month"], "net_worth": h["net_worth"], "assets": h["assets"], "liabilities": h["liabilities"]} for h in hist],
        "change_over_period": r(change_12m),
    }


def _fd_value(f) -> float:
    years = max(0.0, (AS_OF - f["start_date"]).days / 365.25)
    return f["principal"] * (1 + f["interest_rate"] / 100 / 4) ** (4 * years)  # quarterly compounding


def asset_allocation(ident: Identity) -> dict:
    eq = sum(s["quantity"] * s["current_price"] for s in ident.stocks)
    eq += sum(_mf_value(f) for f in ident.mfs if f["fund_type"] in EQUITY_MF)
    eq += sum(_mf_value(f) * 0.65 for f in ident.mfs if f["fund_type"] == "hybrid")
    nps = sum(o["value"] for o in ident.other_assets if o["kind"] == "nps")
    eq += nps * 0.5
    debt = sum(_mf_value(f) for f in ident.mfs if f["fund_type"] == "debt")
    debt += sum(_mf_value(f) * 0.35 for f in ident.mfs if f["fund_type"] == "hybrid")
    debt += sum(_fd_value(f) for f in ident.fds)
    debt += sum(o["value"] for o in ident.other_assets if o["kind"] in {"epf", "ppf"}) + nps * 0.5
    gold = sum(o["value"] for o in ident.other_assets if o["kind"] == "gold")
    re_ = sum(p["current_value"] for p in ident.properties)
    cash = sum(a["balance"] for a in ident.accounts) + sum(o["value"] for o in ident.other_assets if o["kind"] == "cash")
    tot = eq + debt + gold + re_ + cash
    alloc = {"Equity": eq, "Debt": debt, "Gold": gold, "Real estate": re_, "Cash": cash}
    financial = eq + debt + gold + cash
    age = ident.user["age"]
    target_equity = max(30, min(80, 110 - age))  # common "110 minus age" rule of thumb (financial assets only)
    actual_equity_fin = pct(eq, financial) or 0
    return {
        "allocation": {k: r(v) for k, v in alloc.items()},
        "allocation_pct": {k: pct(v, tot) for k, v in alloc.items()},
        "financial_assets_equity_pct": actual_equity_fin,
        "suggested_equity_pct_for_age": target_equity,
        "equity_gap_pct": r(actual_equity_fin - target_equity),
        "note": "Suggested equity share uses the '110 minus age' rule of thumb, bounded to 30-80%, on financial assets only.",
    }


def liquidity(ident: Identity, avg_monthly_expenses: float, essential_monthly: float) -> dict:
    immediate = sum(a["balance"] for a in ident.accounts) + sum(o["value"] for o in ident.other_assets
                                                                  if o["kind"] == "cash" or (o["kind"] == "gold" and o["liquidity"] == "liquid"))
    week = sum(_mf_value(f) for f in ident.mfs if f["fund_type"] == "debt") + sum(_fd_value(f) for f in ident.fds)
    market = sum(s["quantity"] * s["current_price"] for s in ident.stocks) + sum(_mf_value(f) for f in ident.mfs if f["fund_type"] != "debt")
    locked = sum(o["value"] for o in ident.other_assets if o["liquidity"] == "locked") + \
        sum(o["value"] for o in ident.other_assets if o["kind"] == "gold" and o["liquidity"] == "semi_liquid") + \
        sum(p["current_value"] for p in ident.properties)
    emergency_pool = immediate + week
    return {
        "immediate": r(immediate), "within_a_week": r(week), "market_linked": r(market), "locked": r(locked),
        "emergency_pool": r(emergency_pool),
        "emergency_fund_months": r(emergency_pool / avg_monthly_expenses) if avg_monthly_expenses else None,
        "emergency_fund_target_months": 6,
        "emergency_fund_gap": r(max(0.0, 6 * avg_monthly_expenses - emergency_pool)) if avg_monthly_expenses else None,
        "runway_months": r(emergency_pool / avg_monthly_expenses) if avg_monthly_expenses else None,
        "runway_months_essentials_only": r(emergency_pool / essential_monthly) if essential_monthly else None,
        "expenses_known": bool(avg_monthly_expenses),
        "runway_months_incl_market": r((emergency_pool + market) / avg_monthly_expenses) if avg_monthly_expenses else None,
        "definition": "Runway = (bank + cash + liquid gold + FDs + debt funds) / average monthly expenses. "
                      "Equity is excluded because it can fall in value exactly when you need it.",
    }


# ================================================================ known fixed commitments
_PER_MONTH = {"monthly": 1.0, "quarterly": 1 / 3, "yearly": 1 / 12}


def commitments(ident: Identity, emergency_pool: float) -> dict:
    """Fixed monthly outflows the person has told us about (or that follow from their records): recurring payments,
    loan EMIs, active SIPs and insurance premiums. These are commitments, not measured spending - living costs such as
    food and travel are not included - so they are reported separately and never used as 'expenses'."""
    rec = [{"name": p["name"], "category": p["category"], "monthly": r(p["amount"] * _PER_MONTH.get(p["frequency"], 1.0))}
           for p in ident.recurring]
    parts = {"Recurring payments": sum(x["monthly"] for x in rec),
             "Loan EMIs": sum(l["emi"] for l in ident.loans),
             "Active SIPs": sum(s["amount"] for s in ident.sips if s["status"] == "active"),
             "Insurance premiums": sum(p["annual_premium"] for p in ident.insurance) / 12}
    total = sum(parts.values())
    return {"monthly_total": r(total), "parts": {k: r(v) for k, v in parts.items() if v}, "recurring_payments": rec,
            "liquid_money_covers_months": r(emergency_pool / total) if total else None,
            "note": "Known fixed commitments only (recurring payments, EMIs, SIPs, insurance). Day-to-day living costs are "
                    "not included, so this is a floor, not your total spending."}


# ================================================================ credit cards
def credit_analysis(ident: Identity) -> dict:
    if not ident.cards:
        return {"has_cards": False, "cards": [], "overall_utilisation_pct": 0.0, "total_limit": 0, "total_outstanding": 0}
    st = pd.DataFrame(ident.card_statements, columns=["card_id", "month", "bill_amount", "paid_amount", "min_due", "payment_status"])
    cards = []
    for c in ident.cards:
        s = st[st["card_id"] == c["id"]].sort_values("month")
        has_hist = len(s) > 0
        last6 = s.tail(6)
        min_only = int((last6["payment_status"] == 0).sum())
        delays = int((last6["payment_status"] > 0).sum())
        revolving = float(s["bill_amount"].iloc[-2] - s["paid_amount"].iloc[-1]) if len(s) > 1 else 0.0
        est_interest_month = max(0.0, revolving) * c["apr"] / 12 / 100
        util = pct(c["outstanding"], c["credit_limit"])
        cards.append({
            "card": f"{c['issuer']} {c['card_name']}", "last4": c["last4"], "limit": r(c["credit_limit"]),
            "outstanding": r(c["outstanding"]), "min_due": r(c["min_due"]), "due_day": c["due_day"], "apr_pct": c["apr"],
            "utilisation_pct": util,
            "utilisation_band": "healthy" if util < 30 else "elevated" if util < 50 else "high" if util < 75 else "critical",
            "statement_history_months": int(len(s)),
            "months_paid_minimum_only_last6": min_only if has_hist else None, "months_delayed_last6": delays if has_hist else None,
            "worst_status_last6": int(last6["payment_status"].max()) if len(last6) else None,
            "est_interest_per_month": r(est_interest_month),
            "statements": [{"month": x["month"], "bill": r(x["bill_amount"]), "paid": r(x["paid_amount"]),
                            "status": int(x["payment_status"])} for _, x in s.iterrows()],
        })
    tl = sum(c["credit_limit"] for c in ident.cards)
    to = sum(c["outstanding"] for c in ident.cards)
    return {"has_cards": True, "cards": cards, "total_limit": r(tl), "total_outstanding": r(to),
            "overall_utilisation_pct": pct(to, tl),
            "est_interest_per_month": r(sum(c["est_interest_per_month"] for c in cards)),
            "note": "Utilisation under 30% is generally considered healthy for credit scores."}


# ================================================================ loans / debt
def debt_analysis(ident: Identity, avg_income: float) -> dict:
    debts = [{"name": f"{l['loan_type']} ({l['lender']})", "balance": l["balance"], "rate": l["interest_rate"],
              "payment": l["emi"], "kind": "loan", "remaining_months": l["remaining_months"]} for l in ident.loans]
    for c in ident.cards:
        if c["outstanding"] > 0:
            debts.append({"name": f"{c['issuer']} {c['card_name']} card", "balance": c["outstanding"], "rate": c["apr"],
                          "payment": max(c["min_due"], c["outstanding"] * 0.05), "kind": "card", "remaining_months": None})
    total_emi = sum(l["emi"] for l in ident.loans)
    ratio = pct(total_emi, avg_income)
    if not ident.loans:
        band = "none"
    elif ratio is None:
        band = "unknown"  # loans exist but income is not known
    else:
        band = "low" if ratio < 20 else "moderate" if ratio < 35 else "high" if ratio < 50 else "very high"
    total_bal = sum(d["balance"] for d in debts)
    wavg = sum(d["balance"] * d["rate"] for d in debts) / total_bal if total_bal else 0.0
    loans = []
    for l in sorted(ident.loans, key=lambda x: -x["interest_rate"]):
        remaining_interest = l["emi"] * l["remaining_months"] - l["balance"]
        loans.append({"loan_type": l["loan_type"], "lender": l["lender"], "principal": r(l["principal"]),
                      "balance": r(l["balance"]), "emi": r(l["emi"]), "interest_rate": l["interest_rate"],
                      "remaining_months": l["remaining_months"], "remaining_interest": r(max(0.0, remaining_interest)),
                      "emi_share_of_income_pct": pct(l["emi"], avg_income),
                      "secured_by_property": l.get("property_id") is not None})
    return {
        "has_debt": bool(debts), "loans": loans, "total_emi": r(total_emi), "emi_to_income_pct": ratio,
        "risk_band": band, "total_debt": r(total_bal), "weighted_avg_rate_pct": r(wavg),
        "highest_rate_debt": max(debts, key=lambda d: d["rate"])["name"] if debts else None,
        "payoff": payoff_strategies(debts, extra=0.0) if debts else None,
        "debts": [{k: (r(v) if isinstance(v, float) else v) for k, v in d.items()} for d in debts],
        "note": "EMI-to-income bands: <20% low, 20-35% moderate, 35-50% high, 50%+ very high.",
    }


def simulate_payoff(debts: list[dict], extra: float, order: str, max_months: int = 600) -> dict:
    """Month-by-month payoff. order = 'avalanche' (highest rate first) or 'snowball' (smallest balance first)."""
    ds = [dict(d) for d in debts if d["balance"] > 0]
    total_interest, month = 0.0, 0
    freed = 0.0
    payoff_order = []
    while any(d["balance"] > 0.5 for d in ds) and month < max_months:
        month += 1
        for d in ds:
            if d["balance"] > 0:
                it = d["balance"] * d["rate"] / 12 / 100
                d["balance"] += it
                total_interest += it
        pool = extra + freed
        for d in ds:
            if d["balance"] > 0:
                pay = min(d["payment"], d["balance"])
                d["balance"] -= pay
        live = [d for d in ds if d["balance"] > 0.5]
        live.sort(key=(lambda d: -d["rate"]) if order == "avalanche" else (lambda d: d["balance"]))
        for d in live:
            if pool <= 0:
                break
            pay = min(pool, d["balance"])
            d["balance"] -= pay
            pool -= pay
        for d in ds:
            if d["balance"] <= 0.5 and not d.get("_done"):
                d["_done"] = True
                freed += d["payment"]
                payoff_order.append({"debt": d["name"], "paid_off_in_month": month})
    return {"months_to_debt_free": month, "total_interest": round(total_interest, 0), "payoff_order": payoff_order}


def payoff_strategies(debts: list[dict], extra: float = 0.0) -> dict:
    av = simulate_payoff(debts, extra, "avalanche")
    sb = simulate_payoff(debts, extra, "snowball")
    return {"extra_monthly_payment": extra, "avalanche": av, "snowball": sb,
            "interest_saved_by_avalanche": round(sb["total_interest"] - av["total_interest"], 0)}


# ================================================================ protection
def insurance_analysis(ident: Identity, avg_income: float | None) -> dict:
    term = sum(p["cover"] for p in ident.insurance if p["kind"] == "term")
    health = sum(p["cover"] for p in ident.insurance if p["kind"] == "health")
    needed_term = 10 * avg_income * 12 + sum(l["balance"] for l in ident.loans) if avg_income else None
    dependants_likely = ident.user["age"] >= 30 or bool(ident.loans)
    return {
        "term_cover": r(term), "recommended_term_cover": r(needed_term),
        "term_gap": r(max(0.0, needed_term - term)) if needed_term is not None else None,
        "income_known": bool(avg_income),
        "health_cover": r(health), "recommended_health_cover": 1000000.0,
        "health_gap": r(max(0.0, 1000000.0 - health)),
        "has_term": term > 0, "has_health": health > 0, "dependants_likely": dependants_likely,
        "policies": [{"kind": p["kind"], "insurer": p["insurer"], "cover": r(p["cover"]), "annual_premium": r(p["annual_premium"])} for p in ident.insurance],
        "note": "Term cover rule of thumb: 10x annual income + outstanding loans. Health: at least Rs 10 lakh in a metro.",
    }


# ================================================================ investments
def investment_analysis(ident: Identity, avg_income: float) -> dict:
    holdings = []
    for s in ident.stocks:
        inv, cur = s["quantity"] * s["avg_buy_price"], s["quantity"] * s["current_price"]
        yrs = max(0.25, (AS_OF - s["buy_date"]).days / 365.25)
        holdings.append({"type": "Stock", "name": s["company"], "symbol": s["symbol"], "sector": s["sector"],
                         "invested": r(inv), "current": r(cur), "gain": r(cur - inv), "gain_pct": pct(cur - inv, inv),
                         "cagr_pct": r(((cur / inv) ** (1 / yrs) - 1) * 100) if inv > 0 else None, "years_held": r(yrs, 1)})
    for f in ident.mfs:
        inv, cur = f["units"] * f["avg_nav"], f["units"] * f["current_nav"]
        yrs = max(0.25, (AS_OF - f["start_date"]).days / 365.25)
        holdings.append({"type": "Mutual fund", "name": f["scheme"], "symbol": None, "sector": f"MF - {f['fund_type']}",
                         "invested": r(inv), "current": r(cur), "gain": r(cur - inv), "gain_pct": pct(cur - inv, inv),
                         "cagr_pct": None, "years_held": r(yrs, 1),
                         "note": "Returns on SIP-built holdings are absolute; CAGR needs every instalment date (XIRR)."})
    tot_inv = sum(h["invested"] for h in holdings)
    tot_cur = sum(h["current"] for h in holdings)
    eq_stocks = sum(h["current"] for h in holdings if h["type"] == "Stock")
    sectors = {}
    for h in holdings:
        if h["type"] == "Stock":
            sectors[h["sector"]] = sectors.get(h["sector"], 0) + h["current"]
    top_holding = max(holdings, key=lambda h: h["current"]) if holdings else None
    top_sector = max(sectors.items(), key=lambda kv: kv[1]) if sectors else None
    sip_active = [s for s in ident.sips if s["status"] == "active"]
    sip_total = sum(s["amount"] for s in sip_active)
    return {
        "holdings": sorted(holdings, key=lambda h: -h["current"]),
        "total_invested": r(tot_inv), "current_value": r(tot_cur), "total_gain": r(tot_cur - tot_inv),
        "total_gain_pct": pct(tot_cur - tot_inv, tot_inv),
        "sector_exposure": [{"sector": k, "value": r(v), "share_of_stocks_pct": pct(v, eq_stocks)} for k, v in sorted(sectors.items(), key=lambda kv: -kv[1])],
        "top_holding": None if not top_holding else {"name": top_holding["name"], "share_of_portfolio_pct": pct(top_holding["current"], tot_cur)},
        "top_sector": None if not top_sector else {"sector": top_sector[0], "share_of_stocks_pct": pct(top_sector[1], eq_stocks)},
        "stock_count": len(ident.stocks), "fund_count": len(ident.mfs),
        "sips": [{"scheme": s["scheme"], "amount": r(s["amount"]), "status": s["status"], "sip_day": s["sip_day"],
                  "missed_last_12m": s["missed_last_12m"]} for s in ident.sips],
        "sip_monthly_total": r(sip_total), "sip_to_income_pct": pct(sip_total, avg_income),
        "sips_missed_last_12m": int(sum(s["missed_last_12m"] for s in ident.sips)),
        "losing_positions": [h["name"] for h in holdings if (h["gain"] or 0) < 0],
        "prices_as_of": AS_OF.isoformat(),
    }


# ================================================================ idle money & budget
def idle_money(ident: Identity, avg_monthly_expenses: float | None) -> dict:
    if not avg_monthly_expenses:
        return {"available": False, "bank_total": r(sum(a["balance"] for a in ident.accounts)), "operating_buffer": None,
                "idle_in_low_yield_accounts": None, "high_interest_debts": [], "annual_opportunity_cost": None,
                "explanation": "Needs measured monthly expenses to know how much cash is a working buffer."}
    buffer_needed = 1.5 * avg_monthly_expenses
    bank = sum(a["balance"] for a in ident.accounts)
    low_yield = [a for a in ident.accounts if a["interest_rate"] < 4.0]
    low_bal = sum(a["balance"] for a in low_yield)
    idle = max(0.0, low_bal - buffer_needed)
    costly = [l for l in ident.loans if l["interest_rate"] >= 12] + \
             [{"loan_type": f"{c['issuer']} card", "balance": c["outstanding"], "interest_rate": c["apr"]} for c in ident.cards
              if c["outstanding"] > 0 and any(s["payment_status"] >= 0 for s in ident.card_statements if s["card_id"] == c["id"])]
    best_debt_rate = max([d["interest_rate"] for d in costly], default=0.0)
    opp = idle * (best_debt_rate - 3.0) / 100 if costly else idle * (7.0 - 3.0) / 100
    return {"available": True, "bank_total": r(bank), "operating_buffer": r(buffer_needed), "idle_in_low_yield_accounts": r(idle),
            "high_interest_debts": [{"name": d["loan_type"], "balance": r(d["balance"]), "rate": d["interest_rate"]} for d in costly],
            "annual_opportunity_cost": r(opp),
            "explanation": "Idle = money in sub-4% accounts beyond 1.5 months of expenses. Opportunity cost compares it with "
                           "paying off the costliest debt (or a ~7% safe instrument if there is no costly debt)."}


def budget_scenarios(ident: Identity, f: pd.DataFrame, t: pd.DataFrame, income_known: bool = True) -> dict:
    n = len(f)
    if n == 0 or t.empty:
        return {"available": False, "discretionary_monthly_avg": None, "scenarios": [], "category_limits": [],
                "note": "Needs transactions to see discretionary spending."}
    disc = t[t["category"].isin(DISCRETIONARY)].groupby("category")["spend"].sum() / n
    avg_inc, avg_sav = f["income"].mean(), f["savings"].mean()
    scen = []
    for p in (10, 20, 30):
        s = float(disc.sum() * p / 100)
        scen.append({"cut_discretionary_pct": p, "monthly_saving": r(s), "annual_saving": r(s * 12),
                     "new_savings_rate_pct": pct(avg_sav + s, avg_inc) if income_known else None})
    limits = []
    last3 = t[t["month"].isin(sorted(t["month"].unique())[-3:])]
    l3 = last3[last3["category"].isin(DISCRETIONARY)].groupby("category")["spend"].sum() / 3
    for c, v in l3.sort_values(ascending=False).items():
        yr = disc.get(c, v)
        limits.append({"category": c, "last_3m_avg": r(v), "12m_avg": r(yr), "suggested_limit": r(round(min(v, yr) * 0.85, -2)),
                       "overspend_vs_12m_pct": pct(v - yr, yr)})
    return {"available": True, "discretionary_monthly_avg": r(disc.sum()), "scenarios": scen, "category_limits": limits}


def goals_progress(ident: Identity) -> list[dict]:
    out = []
    for g in ident.goals:
        months = max(1, (g["target_date"].year - AS_OF.year) * 12 + g["target_date"].month - AS_OF.month)
        gap = max(0.0, g["target_amount"] - g["current_amount"])
        out.append({"name": g["name"], "target": r(g["target_amount"]), "current": r(g["current_amount"]),
                    "progress_pct": pct(g["current_amount"], g["target_amount"]), "target_date": g["target_date"].isoformat(),
                    "months_left": months, "monthly_needed": r(gap / months),
                    "monthly_needed_at_7pct": r(_pmt_needed(gap, 0.07, months))})
    return out


def _pmt_needed(fv: float, annual: float, months: int) -> float:
    i = annual / 12
    return fv * i / ((1 + i) ** months - 1) if i else fv / months


# ================================================================ health score
MIN_PILLARS_FOR_SCORE = 3


def health_score(cf: dict, liq: dict, cred: dict, debt: dict, ins: dict, inv: dict) -> dict:
    """Transparent 0-100 score from up to 6 equally-weighted pillars (each 0-100).

    A pillar whose inputs are not known is NOT scored (never counted as 0) and is listed under `not_assessed`.
    The score is the average of the assessed pillars, and is withheld when fewer than 3 can be assessed.
    """
    def clamp(x):
        return max(0.0, min(100.0, x))
    inc, spend = cf.get("income_known", True), cf.get("spending_known", True)
    pillars, skipped = {}, {}
    if inc and spend:
        pillars["Savings"] = clamp((cf["avg_savings_rate_pct"] or 0) / 30 * 100)            # 30%+ savings rate = full marks
    else:
        skipped["Savings"] = "needs both income and spending history"
    if spend and liq.get("emergency_fund_months") is not None:
        pillars["Emergency fund"] = clamp(liq["emergency_fund_months"] / 6 * 100)          # 6 months = full
    else:
        skipped["Emergency fund"] = "needs spending history to know monthly expenses"
    if not debt["loans"]:
        pillars["Debt load"] = 100.0                                                        # no loans recorded
    elif debt["emi_to_income_pct"] is not None:
        pillars["Debt load"] = clamp(100 - max(0.0, debt["emi_to_income_pct"] - 10) * 2.5)
    else:
        skipped["Debt load"] = "loans are recorded but income is not"
    pillars["Credit use"] = clamp(100 - max(0.0, (cred.get("overall_utilisation_pct") or 0) - 10) * 1.4)
    term_ok = ins["has_term"] and ins["term_gap"] is not None and ins["term_gap"] <= 0
    pillars["Protection"] = clamp((50 if ins["has_health"] else 0) + (50 if term_ok else 25 if ins["has_term"] else 0))
    if inc:
        pillars["Investing"] = clamp((inv["sip_to_income_pct"] or 0) / 15 * 100)          # 15%+ of income invested monthly = full
    else:
        skipped["Investing"] = "needs income to compare investing against"
    # A score needs at least one pillar measured from real cash-flow data; otherwise "no loans / no cards entered"
    # would make an empty profile look healthy.
    cash_flow_based = {"Savings", "Emergency fund", "Investing"} & set(pillars)
    enough = len(pillars) >= MIN_PILLARS_FOR_SCORE and bool(cash_flow_based)
    score = round(sum(pillars.values()) / len(pillars), 1) if enough else None
    band = None if score is None else "Excellent" if score >= 80 else "Good" if score >= 65 else "Fair" if score >= 45 else "Needs attention"
    return {"score": score, "band": band or "Not enough data", "pillars": {k: round(v, 1) for k, v in pillars.items()},
            "not_assessed": skipped, "assessed_pillars": len(pillars), "partial": bool(skipped),
            "method": "Average of the assessed 0-100 pillars with published thresholds (see each pillar). "
                      "Pillars without data are left out, not scored as zero."}

"""Finora Plan: financial picture, diagnosis, ranked actions and the scenario engine.

The scenario engine applies plan assumptions ON TOP OF the unchanged history. It never writes transactions, never
changes balances and never pretends that a payment happened: every input comes from the cached analysis (itself built
from the stored records) and the assumptions are only added in memory.

Five outcome metrics, each computed the same way for the baseline (no assumptions) and for a scenario:
  surplus          monthly income - monthly expenses (+ spending cut - money the plan commits each month:
                   extra debt repayment, emergency-fund contribution, new SIP). What is left unallocated each month.
  debt_free        month-by-month payoff of every recorded loan and card (highest rate first) with the extra repayment;
                   the existing calculations.simulate_payoff.
  runway (12 mo)   emergency pool in 12 months / monthly expenses. Pool in 12 months = today's pool
                   + 12 x emergency-fund contribution - recorded goals due within 12 months (paid from savings on their
                   date; a delayed purchase moves that date).
  health (12 mo)   the existing calculations.health_score with the scenario's savings rate, emergency-fund months
                   (runway in 12 months) and SIP-to-income; debt, credit and protection pillars are left as recorded.
  fire_age         the existing fire.project with the scenario's monthly investment and retirement expenses.

An action's impact = scenario(that action) - baseline, metric by metric. Nothing is hard-coded; tests assert this.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from ..data.generator import DISCRETIONARY
from . import calculations as C
from . import fire as F

HORIZON_MONTHS = 12
KINDS = {
    "extra_debt_repayment": "Extra debt repayment",
    "spending_cap": "Spending cap",
    "emergency_fund_contribution": "Emergency-fund contribution",
    "sip": "New SIP",
    "delayed_purchase": "Delayed purchase",
}
DETAIL_LINKS = [  # recommendation code prefix -> page that shows the evidence
    (("DEFICIT", "LOW_SAVINGS", "TAX_REGIME"), "/budget"), (("CARD_", "DEFAULT_RISK", "HIGH_EMI", "PAYOFF_ORDER", "IDLE_VS_DEBT"), "/credit"),
    (("EMERGENCY_FUND", "IDLE_CASH"), "/accounts"), (("HEALTH_COVER", "TERM_COVER"), "/records"),
    (("SIP_", "INVEST_SURPLUS", "CONCENTRATION", "LOW_EQUITY"), "/investments"), (("VERIFY_TXN",), "/transactions"),
    (("FORECAST_DEFICIT",), "/forecast"), (("FIRE_GAP",), "/fire"), (("OVERSPEND_",), "/insights"), (("ON_TRACK",), "/identity"),
]


def _round(x: float, step: int = 500) -> float:
    return float(max(step, step * round(x / step)))


def _months_after(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


@dataclass
class Base:
    """Everything the scenario engine needs, taken from the analysis of the stored records."""
    income: float | None
    expenses: float | None
    emi: float
    pool: float
    debts: list[dict]
    sip_total: float
    monthly_invest: float | None
    corpus: float | None
    age: int
    retirement_target: int | None
    goals: list[dict]
    analysis: dict
    as_of: date = field(default_factory=lambda: C.AS_OF)

    @property
    def known(self) -> bool:
        return self.income is not None and self.expenses is not None


def base_from(a: dict, goal_rows: list[dict]) -> Base:
    cf, fire = a["cash_flow"], a["fire"]
    inputs = fire.get("inputs") or {}
    goals = []
    for g in goal_rows:
        months = max(1, (g["target_date"].year - C.AS_OF.year) * 12 + g["target_date"].month - C.AS_OF.month)
        goals.append({"id": g["id"], "name": g["name"], "amount": float(g["target_amount"]), "months_left": months})
    return Base(income=cf.get("avg_monthly_income"), expenses=cf.get("avg_monthly_expenses"),
                emi=float(a["debt"].get("total_emi") or 0.0), pool=float(a["liquidity"].get("emergency_pool") or 0.0),
                debts=[{"name": d["name"], "balance": d["balance"], "rate": d["rate"], "payment": d["payment"]}
                       for d in a["debt"].get("debts") or []],
                sip_total=float(a["investments"].get("sip_monthly_total") or 0.0),
                monthly_invest=inputs.get("monthly_investment") if fire.get("available") else None,
                corpus=inputs.get("current_corpus") if fire.get("available") else None,
                age=int(a["profile"]["age"]), retirement_target=a["profile"].get("retirement_age_target"),
                goals=goals, analysis=a)


# ---------------------------------------------------------------- the scenario engine
def evaluate(b: Base, assumptions: list[dict]) -> dict:
    """Metrics for the baseline (assumptions=[]) or a scenario. Pure: reads b, writes nothing."""
    extra = sum(x["params"]["amount"] for x in assumptions if x["kind"] == "extra_debt_repayment")
    cut = sum(x["params"]["amount"] for x in assumptions if x["kind"] == "spending_cap")
    ef = sum(x["params"]["amount"] for x in assumptions if x["kind"] == "emergency_fund_contribution")
    sip = sum(x["params"]["amount"] for x in assumptions if x["kind"] == "sip")
    delays = {x["params"]["goal_id"]: x["params"]["months_delay"] for x in assumptions if x["kind"] == "delayed_purchase"}
    out: dict = {"inputs": {"extra_debt_repayment": extra, "spending_cut": cut, "emergency_fund_contribution": ef, "new_sip": sip,
                            "delayed_goals": delays}}
    # surplus
    if b.known:
        out["surplus"] = round(b.income - b.expenses + cut - extra - ef - sip, 2)
        out["committed_by_plan"] = round(extra + ef + sip, 2)
    else:
        out["surplus"] = None
    # debt-free date
    if b.debts:
        p = C.simulate_payoff(b.debts, extra, "avalanche")
        capped = p["months_to_debt_free"] >= 600
        out["debt_free_months"] = None if capped else p["months_to_debt_free"]
        out["debt_free_date"] = None if capped else _months_after(b.as_of, p["months_to_debt_free"]).isoformat()
        out["debt_interest"] = None if capped else p["total_interest"]   # a never-cleared debt has no meaningful interest total
    else:
        out["debt_free_months"], out["debt_free_date"], out["debt_interest"] = 0, None, 0.0
    out["has_debt"] = bool(b.debts)
    # runway in 12 months (goals due inside the horizon are paid from savings on their date)
    exp = None if b.expenses is None else max(1.0, b.expenses - cut)
    due = [g for g in b.goals if g["months_left"] + delays.get(g["id"], 0) <= HORIZON_MONTHS]
    pool12 = max(0.0, b.pool + HORIZON_MONTHS * ef - sum(g["amount"] for g in due))
    out["pool_in_12m"] = round(pool12, 2)
    out["goals_paid_within_12m"] = [{"name": g["name"], "amount": g["amount"], "in_months": g["months_left"] + delays.get(g["id"], 0)} for g in due]
    out["runway_months"] = None if exp is None else round(pool12 / exp, 2)
    # health score in 12 months: same function, scenario inputs
    a = b.analysis
    cf = dict(a["cash_flow"])
    if b.known:
        cf["avg_savings_rate_pct"] = C.pct(b.income - (b.expenses - cut), b.income)
    liq = {**a["liquidity"], "emergency_fund_months": out["runway_months"]}
    inv = {**a["investments"], "sip_to_income_pct": C.pct(b.sip_total + sip, b.income) if b.income else None}
    hs = C.health_score(cf, liq, a["credit"], a["debt"], a["insurance"], inv)
    out["health_score"], out["health_pillars"] = hs["score"], hs["pillars"]
    # FIRE age
    if b.monthly_invest is not None and b.corpus is not None and b.expenses is not None:
        retire_exp = max(1.0, (b.expenses - cut - b.emi) * 12)
        fp = F.project(b.corpus, b.monthly_invest + sip, b.age, retire_exp, retirement_age_target=b.retirement_target)
        out["fire_age"] = fp["fire_age"]
        out["corpus_at_target_age"] = fp["corpus_at_target_age"]
        out["fire_number"] = fp["fire_number"]
    else:
        out["fire_age"] = out["corpus_at_target_age"] = out["fire_number"] = None
    return out


def compare(base: dict, scen: dict) -> dict:
    """scenario - baseline for every metric (None when either side is unknown)."""
    def d(k):
        x, y = base.get(k), scen.get(k)
        return None if x is None or y is None else round(y - x, 2)
    return {"surplus": d("surplus"), "runway_months": d("runway_months"), "health_score": d("health_score"),
            "fire_age": d("fire_age"), "debt_free_months": d("debt_free_months"), "debt_interest": d("debt_interest"),
            "pool_in_12m": d("pool_in_12m"), "corpus_at_target_age": d("corpus_at_target_age")}


def benefit(delta: dict, base: dict, scen: dict) -> float:
    """Ranking score (higher = better), published so the order can be explained:
    health points + 3 x runway months + 0.5 x months sooner debt-free + 4 x years earlier FIRE + interest saved / 10,000."""
    s = (delta["health_score"] or 0) + 3 * (delta["runway_months"] or 0) - 0.5 * (delta["debt_free_months"] or 0) \
        - 4 * (delta["fire_age"] or 0) - (delta["debt_interest"] or 0) / 10000
    if base.get("fire_age") is None and scen.get("fire_age") is not None:
        s += 40                                                     # FIRE becomes reachable at all
    return round(s, 2)


# ---------------------------------------------------------------- actions
def candidate_actions(b: Base) -> list[dict]:
    """Concrete, specific candidate actions from the person's own numbers. Amounts are proposals the person can edit."""
    a = b.analysis
    out = []
    if not b.known:
        return out
    surplus = b.income - b.expenses
    bud = a.get("budget") or {}
    limits = bud.get("category_limits") or []
    top = next((l for l in limits if l["category"] in DISCRETIONARY), None)
    # 1. spending cap on the largest lifestyle category (useful in deficit too)
    if top and top["last_3m_avg"] and top["suggested_limit"] is not None and top["last_3m_avg"] - top["suggested_limit"] >= 300:
        cutv = _round(top["last_3m_avg"] - top["suggested_limit"], 100)
        out.append({"code": "PLAN_SPENDING_CAP", "kind": "spending_cap", "params": {"amount": cutv, "category": top["category"]},
                    "title": f"Cap {top['category']} at {_inr(top['last_3m_avg'] - cutv)} a month",
                    "step": f"Keep {top['category']} spending to {_inr(top['last_3m_avg'] - cutv)} a month (you averaged "
                            f"{_inr(top['last_3m_avg'])} over the last 3 months).",
                    "evidence": f"{top['category']} averaged {_inr(top['last_3m_avg'])}/month in the last 3 months and "
                                f"{_inr(top['12m_avg'])}/month over the whole history.",
                    "detail_link": "/budget"})
    room = max(0.0, surplus) + (out[0]["params"]["amount"] if out else 0.0)
    if room >= 1000:
        # 2. extra repayment on the highest-rate debt
        if b.debts:
            hi = max(b.debts, key=lambda d: d["rate"])
            amt = _round(min(0.3 * room, max(500.0, sum(d["balance"] for d in b.debts) / 24)))
            out.append({"code": "PLAN_EXTRA_DEBT", "kind": "extra_debt_repayment", "params": {"amount": amt, "target": hi["name"]},
                        "title": f"Pay {_inr(amt)} extra a month on your debts",
                        "step": f"Add {_inr(amt)} a month to {hi['name']} ({hi['rate']}% - your highest rate); when it is "
                                "cleared, move the payment to the next-highest rate.",
                        "evidence": f"{len(b.debts)} debt(s) totalling {_inr(sum(d['balance'] for d in b.debts))}; highest rate "
                                    f"{hi['rate']}% on {hi['name']}.",
                        "detail_link": "/credit"})
        # 3. emergency fund
        ef_months = a["liquidity"].get("emergency_fund_months")
        gap = a["liquidity"].get("emergency_fund_gap") or 0.0
        if ef_months is not None and ef_months < 6 and gap > 0:
            amt = _round(min(gap / 12, 0.4 * room))
            out.append({"code": "PLAN_EMERGENCY_FUND", "kind": "emergency_fund_contribution", "params": {"amount": amt},
                        "title": f"Put {_inr(amt)} a month into your emergency fund",
                        "step": f"Move {_inr(amt)} to a separate savings account or liquid fund each month until it covers 6 months "
                                f"of expenses ({_inr(6 * b.expenses)}).",
                        "evidence": f"Your emergency pool of {_inr(b.pool)} covers {ef_months:.1f} months of expenses; the target is 6.",
                        "detail_link": "/accounts"})
        # 4. SIP
        sip_pct = a["investments"].get("sip_to_income_pct")
        fire = a.get("fire") or {}
        fire_gap = None
        if fire.get("available") and fire.get("on_track") is False and fire.get("monthly_investment_needed_for_target") and b.monthly_invest is not None:
            fire_gap = max(0.0, fire["monthly_investment_needed_for_target"] - b.monthly_invest)
        if sip_pct is None or sip_pct < 15 or fire_gap:
            need = fire_gap if fire_gap else max(500.0, 0.15 * b.income - b.sip_total)
            amt = _round(min(0.3 * room, need))
            why = (f"To retire at {fire['retirement_age_target']} you would need to invest about "
                   f"{_inr(fire['monthly_investment_needed_for_target'])}/month; you invest {_inr(b.monthly_invest)}."
                   if fire_gap else
                   f"You invest {_inr(b.sip_total)}/month in SIPs ({sip_pct if sip_pct is not None else 0:.0f}% of income); "
                   "15% is the usual guideline.")
            out.append({"code": "PLAN_SIP", "kind": "sip", "params": {"amount": amt},
                        "title": f"Start a {_inr(amt)} monthly SIP",
                        "step": f"Set up a {_inr(amt)} monthly SIP in a diversified index fund on the day after your salary arrives.",
                        "evidence": why, "detail_link": "/investments"})
    # 5. delayed purchase: a goal inside the horizon that would drain the emergency pool
    if b.expenses:
        for g in sorted(b.goals, key=lambda g: g["months_left"]):
            if g["months_left"] <= HORIZON_MONTHS and b.pool - g["amount"] < 3 * b.expenses:
                # past the 12-month window, and long enough that saving half the surplus each month covers it
                delay = max(HORIZON_MONTHS + 1 - g["months_left"],
                            0 if surplus <= 0 else math.ceil(g["amount"] / max(1.0, 0.5 * surplus)) - g["months_left"])
                out.append({"code": f"PLAN_DELAY_{g['id']}", "kind": "delayed_purchase",
                            "params": {"goal_id": g["id"], "months_delay": int(min(60, delay)), "amount": g["amount"]},
                            "title": f"Delay {g['name']} by {int(min(60, delay))} months",
                            "step": f"Move the {g['name']} purchase ({_inr(g['amount'])}) from {g['months_left']} to "
                                    f"{g['months_left'] + int(min(60, delay))} months from now and save towards it meanwhile.",
                            "evidence": f"Paying {_inr(g['amount'])} from savings in {g['months_left']} months would leave "
                                        f"{_inr(max(0.0, b.pool - g['amount']))} - under 3 months of expenses.",
                            "detail_link": "/records"})
                break
    return out


def _inr(x) -> str:
    x = float(x or 0)
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


def headline_impact(kind: str, params: dict, delta: dict) -> dict:
    """The one rupee figure shown on an action, derived from the scenario (never typed in)."""
    if kind == "extra_debt_repayment":
        if delta["debt_interest"] is None:     # at current payments a debt is never cleared, so there is no saving to compare
            return {"inr": None, "label": "a debt that is otherwise never paid off gets a payoff date"}
        return {"inr": -delta["debt_interest"], "label": "interest saved"}
    if kind == "spending_cap":
        return {"inr": (delta["surplus"] or 0) * 12, "label": "freed per year"}
    if kind in ("emergency_fund_contribution", "delayed_purchase"):
        return {"inr": delta["pool_in_12m"] or 0, "label": "more savings in 12 months"}
    if kind == "sip":
        return {"inr": delta["corpus_at_target_age"] or 0, "label": "more by your target retirement age (today's ₹)"}
    return {"inr": 0, "label": ""}


def rank_actions(b: Base, baseline: dict, accepted: list[dict], dismissed: set[str]) -> list[dict]:
    taken = {x.get("source_code") for x in accepted}
    acts = []
    for c in candidate_actions(b):
        scen = evaluate(b, [c])
        delta = compare(baseline, scen)
        c = {**c, "kind_label": KINDS[c["kind"]], "baseline": _metrics(baseline), "scenario": _metrics(scen), "effect": delta,
             "impact": headline_impact(c["kind"], c["params"], delta), "benefit": benefit(delta, baseline, scen),
             "status": "accepted" if c["code"] in taken else "dismissed" if c["code"] in dismissed else "open"}
        if c["benefit"] > 0 or c["status"] != "open":
            acts.append(c)
    acts.sort(key=lambda x: -x["benefit"])
    for i, x in enumerate(acts, 1):
        x["rank"] = i
    return acts[:5]


def _metrics(m: dict) -> dict:
    return {k: m.get(k) for k in ("surplus", "debt_free_date", "debt_free_months", "runway_months", "health_score", "fire_age",
                                  "debt_interest", "pool_in_12m", "corpus_at_target_age", "has_debt")}


# ---------------------------------------------------------------- diagnosis & picture
def _link(code: str) -> str:
    for prefixes, link in DETAIL_LINKS:
        if code.startswith(prefixes):
            return link
    return "/identity"


def diagnosis(a: dict) -> list[dict]:
    """3 to 6 findings, each with finding, evidence, why it matters, source, confidence/limitation and a detail link."""
    order = {"high": 0, "medium": 1, "low": 2}
    recs = sorted(a.get("recommendations") or [], key=lambda r: order.get(r["priority"], 3))
    out = []
    no_insurance = "Insurance" in ((a.get("completeness") or {}).get("missing") or [])
    for r in recs:
        if no_insurance and r["code"] in ("HEALTH_COVER", "TERM_COVER"):
            # nothing recorded is not the same as no cover: say what is actually known
            if any(x["code"] == "DATA_INSURANCE" for x in out):
                continue
            out.append({"code": "DATA_INSURANCE", "severity": "info", "finding": "No insurance recorded yet",
                        "evidence": "There are no health or term policies on this profile.",
                        "why": "Finora cannot tell whether you are uncovered or simply have not added your policies; "
                               "protection is left out of the plan until you do.",
                        "source": "Data completeness check", "confidence": "Exact (about the data on file, not about your cover).",
                        "detail_link": "/records"})
            continue
        model = "model" in (r.get("source") or "").lower() or r["code"] in ("DEFAULT_RISK", "VERIFY_TXN", "FORECAST_DEFICIT")
        out.append({"code": r["code"], "severity": r["priority"], "finding": r["finding"], "evidence": r["evidence"],
                    "why": r["explanation"], "source": r.get("source") or "Financial calculations",
                    "confidence": ("Model estimate on your history; see Model Lab for how it was trained and its limits."
                                   if model else "Rule applied to your recorded numbers; exact for the data on file."),
                    "detail_link": _link(r["code"])})
        if len(out) == 6:
            break
    comp = a.get("completeness") or {}
    essential = ["Income", "Spending history", "Bank accounts", "Three months of history", "Investments", "Insurance"]
    for name in [m for m in essential if m in (comp.get("missing") or [])]:
        if len(out) >= 3:
            break
        out.append({"code": f"DATA_{name.upper().replace(' ', '_')[:30]}", "severity": "info", "finding": f"Missing: {name}",
                    "evidence": f"Your profile is {comp.get('score_pct', 0)}% complete.",
                    "why": "Without it some parts of the plan cannot be calculated; Finora never fills it in for you.",
                    "source": "Data completeness check", "confidence": "Exact.", "detail_link": "/records"})
    cf = a["cash_flow"]
    if len(out) < 3 and cf.get("avg_savings_rate_pct") is not None and cf["avg_savings_rate_pct"] >= 20:
        out.append({"code": "STRENGTH_SAVINGS", "severity": "good", "finding": f"You save {cf['avg_savings_rate_pct']:.0f}% of your income",
                    "evidence": f"Average surplus {_inr(cf['avg_monthly_savings'])} a month.",
                    "why": "A 20%+ savings rate is the base everything else in the plan is built on.",
                    "source": "Financial calculations", "confidence": "Exact for the data on file.", "detail_link": "/budget"})
    return out


def picture(a: dict) -> dict:
    cf, nw, liq, debt, inv, hs, fire = a["cash_flow"], a["net_worth"], a["liquidity"], a["debt"], a["investments"], a["health_score"], a["fire"]
    return {"income": cf.get("avg_monthly_income"), "expenses": cf.get("avg_monthly_expenses"), "surplus": cf.get("avg_monthly_savings"),
            "savings_rate_pct": cf.get("avg_savings_rate_pct"), "balances": liq.get("immediate"), "emergency_pool": liq.get("emergency_pool"),
            "debt": debt.get("total_debt"), "emi": debt.get("total_emi"), "emi_to_income_pct": debt.get("emi_to_income_pct"),
            "net_worth": nw.get("net_worth"), "runway_months": liq.get("runway_months"), "health_score": hs.get("score"),
            "health_band": hs.get("band"), "investments": inv.get("current_value"), "sip_monthly": inv.get("sip_monthly_total"),
            "fire_available": bool(fire.get("available")), "fire_age": fire.get("fire_age"), "fire_progress_pct": fire.get("progress_pct"),
            "fire_target_age": fire.get("retirement_age_target"), "completeness_pct": (a.get("completeness") or {}).get("score_pct"),
            "months_of_data": (cf.get("coverage") or {}).get("months"), "data_notice": a.get("data_notice")}


def build(a: dict, goal_rows: list[dict], accepted: list[dict], dismissed: set[str]) -> dict:
    b = base_from(a, goal_rows)
    baseline = evaluate(b, [])
    actions = rank_actions(b, baseline, accepted, dismissed)
    plan = evaluate(b, accepted)
    out = {"picture": picture(a), "diagnosis": diagnosis(a), "actions": actions,
           "assumptions": accepted, "baseline": _metrics(baseline), "with_plan": _metrics(plan), "plan_effect": compare(baseline, plan),
           "plan_inputs": plan["inputs"], "goals_paid_within_12m": plan["goals_paid_within_12m"],
           "over_committed": None if plan["surplus"] is None else plan["surplus"] < 0,
           "available": b.known,
           "method": {"surplus": "Monthly income - expenses + any spending cut - money the plan sets aside each month.",
                      "debt_free": "Month-by-month payoff of every loan and card, highest interest rate first, with the extra repayment.",
                      "runway": "Emergency pool in 12 months / monthly expenses. Goals due in the next 12 months are paid from savings.",
                      "health": "The Finora health score recomputed with the plan's savings rate, emergency-fund months and SIPs.",
                      "fire": "FIRE projection with the plan's monthly investment and retirement spending.",
                      "ranking": "Health points + 3 x runway months + 0.5 x months sooner debt-free + 4 x years earlier FIRE + interest saved / 10,000.",
                      "history": "Nothing in your recorded transactions or balances is changed. Accepting an action only stores an assumption."}}
    if not b.known:
        out["reason"] = "Finora needs both income and spending history to propose actions and run scenarios."
    return out


def title_for(kind: str, params: dict, goal_name: str | None = None) -> str:
    """The step's title always describes the STORED amount (an edited step must not keep the original wording)."""
    a = params.get("amount")
    if kind == "extra_debt_repayment":
        return f"Pay {_inr(a)} extra a month on your debts"
    if kind == "spending_cap":
        return f"Spend {_inr(a)} less a month" + (f" on {params['category']}" if params.get("category") else "")
    if kind == "emergency_fund_contribution":
        return f"Put {_inr(a)} a month into your emergency fund"
    if kind == "sip":
        return f"Start a {_inr(a)} monthly SIP"
    if kind == "delayed_purchase":
        return f"Delay {goal_name or 'the purchase'} by {params.get('months_delay')} months"
    return KINDS.get(kind, kind)

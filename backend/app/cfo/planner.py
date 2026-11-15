"""AI CFO planner (Phase 7 remediation).

Why: a 3B model asked to pick among ~30 tool schemas in free-form tool calling chose wrong tools, lost follow-up context
and answered "largest transaction" from merchant totals. Here the model's job is narrowed to UNDERSTANDING:

  1. PLAN     one schema-constrained JSON call (Ollama structured output): what the user wants, as 1-3 operations from a
              fixed catalogue with their arguments, or a clarifying question, using the structured conversation state.
  2. RESOLVE  deterministic reference resolution and validation: "same"/"previous" periods, inherited category and filters,
              counts ("top three", "largest"), amounts must come from the user's words, categories/periods must be valid.
  3. EXECUTE  the operations run as read-only tools on the signed-in profile (independent ones in parallel); derived
              figures (differences, % cuts, savings) are computed here, never by the model.
  4. WRITE    the model phrases the answer from THIS turn's results only, with an explicit interpretation of the question.
  5. CHECK    numbers (only this turn's results + the question), currency (₹ vs £), and semantics (the figures the
              operation requires are present, the requested count is respected). Failure: one rewrite, then a template.

Questions outside the catalogue ("other") go to the open tool-calling agent; general questions are answered directly.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import guard, router, tools

# ---------------------------------------------------------------- operation catalogue
OPS = {
    "spend_total": "total spent in a period, optionally one category or merchant",
    "spend_by_category": "where money goes: spending split by category for a period",
    "top_transactions": "the largest INDIVIDUAL transactions (largest / biggest single / top N), optionally a category or merchant",
    "compare_periods": "compare spending between two periods (e.g. last month vs the month before), optionally one category",
    "spending_changes": "which categories went up or down between two months (what is increasing, what changed)",
    "reduce_spending": "how much would be saved by cutting a spending amount by a percent",
    "income_total": "income received in a period",
    "savings": "how much was saved (income minus spending) in a period",
    "balances": "bank account balances, which account has the most money, total cash in banks",
    "net_worth": "net worth: assets minus liabilities",
    "overview": "overall financial picture / analyse my finances / how am I doing",
    "debts": "loans, EMIs, total debt owed, payoff order",
    "credit_cards": "credit cards: outstanding balances, limits, utilisation, dues",
    "credit_risk": "the credit-risk model: chance of missing a card payment and the SHAP reasons",
    "anomalies": "unusual / suspicious transactions flagged by the anomaly scanner",
    "forecast": "next month's spending forecast, money available next month, how reliable the forecast is",
    "peers": "compare with similar people / US household peer groups",
    "category_suggestions": "pending transaction-category suggestions to confirm",
    "investments": "investments, portfolio value, SIP contributions, returns",
    "pause_investing": "what happens if the user stops/pauses SIP investing for some months",
    "goals": "financial goals and how much to save each month to reach them",
    "retirement": "retirement / FIRE: when can I retire, retirement corpus",
    "runway": "how long savings last without income, emergency fund",
    "tax": "income tax: old vs new regime",
    "insurance": "life and health insurance cover",
    "affordability": "can I afford a purchase of a given price (car, phone, holiday, home ...)",
    "what_if": "plan what-if: start/increase a SIP, extra debt repayment, spending cap, emergency-fund contribution",
    "plan": "the Finora Plan: what to focus on, priorities, next steps, why Finora recommends something",
    "health_score": "the Financial Health Score and its pillars (also 'financial discipline')",
    "emi": "EMI for a loan amount, rate and tenure",
    "model_info": "how one of Finora's models works: data, accuracy, limitations, Model Lab",
    "other": "any other question about the user's own finances not covered above",
}
SPEND_OPS = {"spend_total", "spend_by_category", "top_transactions", "compare_periods", "reduce_spending"}
PERIOD_WORDS = ["this_month", "last_month", "last_3_months", "last_6_months", "last_12_months", "all", "same", "previous"]
WHAT_IF_KINDS = ["sip", "extra_debt_repayment", "spending_cap", "emergency_fund_contribution"]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"enum": ["general", "personal", "clarify"]},
        "clarify": {"type": "string"},
        "follows_previous": {"type": "boolean"},
        "steps": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
            "op": {"enum": list(OPS)},
            "category": {"type": ["string", "null"]}, "merchant": {"type": ["string", "null"]},
            "period": {"type": ["string", "null"]}, "period2": {"type": ["string", "null"]},
            "limit": {"type": ["integer", "null"]}, "amount": {"type": ["number", "null"]}, "percent": {"type": ["number", "null"]},
            "months": {"type": ["integer", "null"]}, "item": {"type": ["string", "null"]},
            "what_if_kind": {"type": ["string", "null"]}, "model": {"type": ["string", "null"]}},
            "required": ["op"]}},
    },
    "required": ["kind", "follows_previous", "steps"],
}

PLAN_PROMPT = """You turn a user's message into a plan for Finora, a personal-finance app for one user in India. Output JSON only.
kind: "general" = finance knowledge/concepts, no personal data needed (what is an ETF, explain inflation).
      "personal" = about the user's own money: choose 1-3 steps.
      "clarify" = a follow-up whose reference cannot be resolved from the conversation state; put a short question in "clarify".
follows_previous: true when the message continues the current topic (what about..., compare both, the largest one, those, it, this spending).

Operations (op):
{ops}

Arguments:
- period / period2: "YYYY-MM", or one of: this_month, last_month, last_3_months, last_6_months, last_12_months, all,
  "same" (the period of the current topic), "previous" (the month before the current topic's month). Leave null if not said.
- category: one of {cats}; food/restaurants = Dining. Leave null to keep the current topic's category on a follow-up.
- merchant: a shop/brand name if the user names one. limit: how many items for top_transactions (largest = 1).
- amount: ONLY a rupee amount the user wrote (₹8 lakh = 800000). percent: e.g. 20 for "20%". months: e.g. 6.
- what_if_kind: {wik}. item: what is being bought (car, phone, holiday). model: credit_risk, categoriser, anomaly, forecast, peers.

Calendar: today is {today}; this month = {m0}; last month = {m1}; the month before last = {m2}.

Examples (format only):
"how much did I spend on groceries in August" -> {{"kind":"personal","follows_previous":false,"steps":[{{"op":"spend_total","category":"Groceries","period":"2026-08"}}]}}
then "and the month before?" -> {{"kind":"personal","follows_previous":true,"steps":[{{"op":"spend_total","period":"previous"}}]}}
then "compare the two" -> {{"kind":"personal","follows_previous":true,"steps":[{{"op":"compare_periods"}}]}}
then "what were the 2 biggest purchases" -> {{"kind":"personal","follows_previous":true,"steps":[{{"op":"top_transactions","limit":2,"period":"same"}}]}}
"what is a mutual fund" -> {{"kind":"general","follows_previous":false,"steps":[]}}
"my net worth and my bank balance" -> {{"kind":"personal","follows_previous":false,"steps":[{{"op":"net_worth"}},{{"op":"balances"}}]}}
"is that a lot?" with no current topic -> {{"kind":"clarify","clarify":"What would you like me to compare?","follows_previous":true,"steps":[]}}"""


def _month(ym: str, back: int) -> str:
    return tools._months_back(ym, back)


def plan_messages(question: str, state: dict, recent: list[dict]) -> list[dict]:
    cur = date.today().strftime("%Y-%m")
    system = PLAN_PROMPT.format(ops="\n".join(f"- {k}: {v}" for k, v in OPS.items()), cats=", ".join(tools._ALL_CATS),
                                wik=", ".join(WHAT_IF_KINDS), today=date.today().isoformat(), m0=cur, m1=_month(cur, 1), m2=_month(cur, 2))
    topic = state.get("topic") or {}
    ctx_lines = [f"Current topic: {json.dumps(topic, ensure_ascii=False)}" if topic else "Current topic: none"]
    if state.get("log"):
        ctx_lines.append("Earlier in this conversation (verified results): " + " | ".join(state["log"][-6:]))
    for h in recent[-2:]:
        if h.get("role") == "user":
            ctx_lines.append(f"Previous user message: {h['content'][:200]}")
    return [{"role": "system", "content": system},
            {"role": "user", "content": "\n".join(ctx_lines) + f"\n\nMessage: {question}\nPlan:"}]


# ---------------------------------------------------------------- resolution and validation
def requested_count(question: str) -> int | None:
    q = question.lower()
    m = re.search(r"\b(?:top|biggest|largest|highest|first|last)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", q) or \
        re.search(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:biggest|largest|highest|top|most expensive)\b", q)
    if m:
        v = m.group(1)
        return int(v) if v.isdigit() else NUMBER_WORDS[v]
    if re.search(r"\b(the )?(largest|biggest|highest|most expensive|single largest|biggest single)( one| single)?\b", q) and \
            not re.search(r"\b(categor\w*|merchants?|expenses are|areas?)\b", q):
        return 1
    return None


from ..services.cleaning import CATEGORY_SYNONYMS as _SYN  # noqa: E402

_CAT_WORDS = sorted({**{c.lower(): c for c in tools._ALL_CATS}, **{k: v for k, v in _SYN.items()},
                     "food": "Dining", "eating out": "Dining", "restaurants": "Dining", "coffee": "Dining", "flights": "Travel",
                     "travel": "Travel", "trips": "Travel", "petrol": "Fuel", "medicines": "Health", "doctor": "Health"}.items(),
                    key=lambda kv: -len(kv[0]))
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"


def category_in(question: str) -> str | None:
    """A spending category the user named in their own words (longest match first)."""
    q = question.lower()
    for word, cat in _CAT_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", q) and cat in tools._ALL_CATS:
            return cat
    return None


def explicit_period(question: str) -> bool:
    return bool(re.search(rf"\b({_MONTHS}|\d{{4}}-\d{{2}}|this month|last month|last (\d+|three|six|twelve) months|past (\d+|three|six) months|"
                          r"this year|last year)\b", question, re.I))


_MONTH_NUM = {m: i + 1 for i, m in enumerate(_MONTHS.split("|"))}
_N = {"three": 3, "3": 3, "six": 6, "6": 6, "twelve": 12, "12": 12}


def periods_in(question: str) -> list[str]:
    """The periods the user wrote, in order, as tool periods. These are the user's own words, so they override the planner."""
    q, cur = question.lower(), date.today()
    found = []
    pat = (rf"\b(this month|last month|(?:last|past|previous) (three|six|twelve|3|6|12) months|(?:last|past) year|"
           rf"(\d{{4}})-(\d{{2}})|({_MONTHS})(?:,?\s+(\d{{4}}))?)\b")
    for m in re.finditer(pat, q):
        g = m.group(0)
        if g == "this month":
            p = "this_month"
        elif g == "last month":
            p = "last_month"
        elif m.group(2):
            p = f"last_{_N[m.group(2)]}_months"
        elif "year" in g:
            p = "last_12_months"
        elif m.group(3):
            p = f"{m.group(3)}-{m.group(4)}"
        else:
            mon = _MONTH_NUM[m.group(5)]
            yr = int(m.group(6)) if m.group(6) else (cur.year if mon <= cur.month else cur.year - 1)   # most recent such month
            p = f"{yr}-{mon:02d}"
        if p not in found:
            found.append(p)
    if not found:
        y = re.search(r"\b(?:in|year|during|for)\s+((?:19|20)\d{2})\b", q)
        if y:
            found.append(y.group(1))
    if len([x for x in found if re.fullmatch(r"\d{4}-\d{2}", x)]) >= 2:        # "September and October 2026": share the year
        yrs = re.findall(r"\b(20\d{2})\b", q)
        if len(yrs) == 1:
            found = [f"{yrs[0]}-{x[5:]}" if re.fullmatch(r"\d{4}-\d{2}", x) else x for x in found]
    return found


_CAT_NAMES = {w for w, _ in _CAT_WORDS}


def merchant_in(question: str) -> str | None:
    """A merchant the user named ('at Swiggy', 'from Amazon'): capitalised, not a category word or a month."""
    for m in re.finditer(r"\b(?:at|from)\s+([A-Z][\w&'.]*(?:\s[A-Z][\w&'.]*)?)", question):
        name = m.group(1).strip(" .")
        if name.lower() not in _CAT_NAMES and name.lower().split()[0] not in _MONTH_NUM and name.lower() not in ("finora", "i"):
            return name
    return None


_PERSONAL = re.compile(r"\b(my|mine|me|am i|have i|did i|do i|can i|could i|should i|i (spend|spent|earn|earned|owe|have|had|save|saved|pay|paid))\b|"
                       r"\b(the|finora'?s?|this|your)\s+([\w-]+\s+)?(categori[sz]er|forecast\w*|credit[- ]risk model|anomaly (detector|scanner|model)|"
                       r"scanner|peer (benchmark\w*|model|groups?)|model lab|models?)\b", re.I)


def personal_signal(question: str) -> bool:
    """The message is about the user's own money or about Finora's own models, or asks for a calculation on amounts it gives
    (EMI on ₹10 lakh...): those need Finora's tools/calculators, not general knowledge (a 3B model's arithmetic is not trusted)."""
    return bool(_PERSONAL.search(question)) or bool(router.parse_amounts(question) and
                                                    re.search(r"\b(emi|afford\w*|loan|sip|save|saving)\b", question, re.I))


def clarify_justified(question: str, state: dict) -> bool:
    """The planner may only ask back when the message points at something the conversation does not have."""
    return _bare_reference(question, state)


def _bare_reference(question: str, state: dict) -> bool:
    """A short, purely referential message ('Compare them.', 'Which one was the largest?') with nothing to refer to."""
    return (_refers_back(question) and not (state.get("topic") or state.get("log")) and len(question.split()) <= 8
            and not periods_in(question) and not category_in(question) and not merchant_in(question)
            and not re.search(r"\bmy\b|\b(net worth|balance|income|salary|loan|card|sip|forecast|credit|goal|tax|insurance)\b", question, re.I))


_PERIOD_ALIASES = {"last_three_months": "last_3_months", "past_3_months": "last_3_months", "past_three_months": "last_3_months",
                   "previous_3_months": "last_3_months", "last_quarter": "last_3_months", "last_six_months": "last_6_months",
                   "past_6_months": "last_6_months", "last_twelve_months": "last_12_months", "past_year": "last_12_months",
                   "last_year": "last_12_months", "past_12_months": "last_12_months", "current_month": "this_month",
                   "previous_month": "last_month", "all_time": "all"}


def _norm_period(p: str | None, topic: dict) -> str | None:
    if p is None:
        return None
    p = str(p).strip().lower().replace(" ", "_").replace("-", "_") if not re.fullmatch(r"\d{4}-\d{2}", str(p).strip()) else str(p).strip()
    p = _PERIOD_ALIASES.get(p, p)
    tp = topic.get("period")
    if p == "same":
        return tp
    if p == "previous":
        if tp and re.fullmatch(r"\d{4}-\d{2}", tp):
            return _month(tp, 1)
        if tp == "last_month":
            return _month(date.today().strftime("%Y-%m"), 2)
        return "last_month"
    return p


def _abs_month(p: str | None) -> str | None:
    cur = date.today().strftime("%Y-%m")
    return {"this_month": cur, "last_month": _month(cur, 1)}.get(p, p)


_FIELD_TYPES = {"category": str, "merchant": str, "period": str, "period2": str, "item": str, "what_if_kind": str, "model": str,
                "limit": int, "months": int, "amount": float, "percent": float}


def sanitise(plan) -> tuple[dict, list[str]]:
    """Server-side validation of the model's plan against PLAN_SCHEMA. Ollama's `format` constrains decoding, but the server does
    not trust it: an invalid plan never executes as-is. Unknown kind -> the open tool-calling path (never general by default);
    unknown op -> dropped; mistyped fields -> dropped (later resolution re-derives or asks), never coerced to a different meaning."""
    problems = []
    if not isinstance(plan, dict):
        return {"kind": "personal", "follows_previous": False, "steps": [{"op": "other"}]}, ["plan is not an object"]
    kind = plan.get("kind")
    if kind not in ("general", "personal", "clarify"):
        problems.append(f"invalid kind {kind!r}")
        return {"kind": "personal", "follows_previous": False, "steps": [{"op": "other"}]}, problems
    steps = []
    for st in plan.get("steps") if isinstance(plan.get("steps"), list) else []:
        if not isinstance(st, dict) or st.get("op") not in OPS:
            problems.append(f"dropped invalid step {st!r}"[:120])
            continue
        clean = {"op": st["op"]}
        for k, v in st.items():
            t = _FIELD_TYPES.get(k)
            if t is None or v is None:
                continue
            if t is str and isinstance(v, str) and len(v) <= 60:
                clean[k] = v.strip()
            elif t is int and isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and 0 < v <= 600:
                clean[k] = int(v)
            elif t is float and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 1e10:
                clean[k] = float(v)
            else:
                problems.append(f"dropped {k}={v!r}"[:80])
        steps.append(clean)
    if kind == "personal" and not steps:
        steps = [{"op": "other"}]
        problems.append("personal plan without valid steps")
    out = {"kind": kind, "follows_previous": plan.get("follows_previous") is True, "steps": steps[:3]}
    if kind == "clarify":
        out["clarify"] = str(plan.get("clarify") or "")[:200]
    return out, problems


def resolve(plan: dict, question: str, state: dict, known: dict | None = None) -> tuple[list[dict], list[str]]:
    """Deterministic follow-up resolution + validation. Returns (steps, notes). `known` = what the conversation can resolve
    references against (defaults to the state)."""
    topic = state.get("topic") or {}
    follow = bool(plan.get("follows_previous")) or _refers_back(question)
    steps, notes = [], []
    asked = router.parse_amounts(question)
    count = requested_count(question)
    pct = re.search(r"(\d+(?:\.\d+)?)\s*(%|percent)", question)
    months = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+months?\b", question.lower())
    planned = [dict(x) for x in (plan.get("steps") or [])[:3]]
    if re.search(r"\b(EMIs?|SIPs?)\b", question, re.I) and not re.search(r"\bspen[dt]\w*\b", question, re.I):
        # 'my EMIs' / 'my SIPs' are loan instalments and investment contributions, not a spending category of transactions
        drop = [x for x in planned if x.get("op") in SPEND_OPS and (str(x.get("category") or "").lower() in ("emi", "investment", "investments")
                                                                   or re.search(r"invest|emi|sip", str(x.get("merchant") or ""), re.I))]
        if drop:
            planned = [x for x in planned if x not in drop]
            notes.append("EMIs/SIPs are read from your loans and investments, not from spending")
    if planned and re.search(r"\bcompare\b", question, re.I):
        for x in planned:                                   # 'compare X with Y' over spending is a comparison, not a list or one total
            if x.get("op") in ("top_transactions", "spend_total") and (x.get("period2") or (len(periods_in(question)) >= 1 and _refers_back(question))
                                                                       or len(periods_in(question)) >= 2):
                x["op"] = "compare_periods"
                x.pop("limit", None)
    have0 = {x.get("op") for x in planned}
    for pat, cop in COVERAGE:                           # a clear request in the message must not be dropped; added BEFORE validation
        if cop not in have0 and len(planned) < 3 and re.search(pat, question, re.I) and not (cop == "investments" and "pause_investing" in have0) \
                and not (cop == "debts" and "emi" in have0):
            planned.append({"op": cop})
            have0.add(cop)
            notes.append(f"added {cop} for the part of your message that asked for it")
    for s in planned:
        s = {k: v for k, v in s.items() if v not in (None, "")}
        op = s.get("op")
        if op not in OPS:
            continue
        for k in ("period", "period2"):
            if k in s:
                s[k] = _norm_period(s[k], topic)
        named = category_in(question)
        merch = merchant_in(question)
        if op in SPEND_OPS and merch and not (named and s.get("category") == named):
            s.pop("category", None)                        # 'at Swiggy' is a merchant, not the planner's guess of its category
            s["merchant"] = merch
        said = periods_in(question)
        if op in SPEND_OPS | {"income_total", "savings"}:
            if op == "compare_periods" and len(said) >= 2:
                s["period"], s["period2"] = sorted(said[:2], key=lambda p: _abs_month(p) or p, reverse=True)
            elif op == "compare_periods" and len(said) == 1:
                s["period"] = said[0]
                if follow and topic.get("period") and _abs_month(topic["period"]) != _abs_month(said[0]):
                    s["period"], s["period2"] = sorted([said[0], topic["period"]], key=lambda p: _abs_month(p) or p, reverse=True)
            elif len(said) == 1:
                if s.get("period") and _abs_month(s["period"]) != _abs_month(said[0]):
                    notes.append(f"period set to {said[0]}, as written in your message")
                s["period"] = said[0]
        if op in SPEND_OPS and named and not s.get("category") and not s.get("merchant"):
            s["category"] = named                          # the user named a category: the plan must use it
        if op == "spend_by_category" and (s.get("category") or s.get("merchant") or named or merch):
            op = s["op"] = "spend_total"                   # a named category is a total for that category, not a breakdown
        if op == "anomalies" and follow and topic.get("category") and not s.get("category"):
            s["category"] = topic["category"]                 # 'is that spending unusual?' -> focus on the category discussed
        if op in SPEND_OPS and follow:                    # inherit the topic's filters on a follow-up
            for k in ("category", "merchant"):
                if k not in s and topic.get(k):
                    s[k] = topic[k]
            if "period" not in s and topic.get("period"):
                s["period"] = topic["period"]
        if s.get("category"):
            c = tools._std_cat(s["category"])
            if str(s["category"]).lower() in ("all", "any", "total", "everything"):
                s.pop("category")
            elif c not in tools._ALL_CATS:
                s.setdefault("merchant", s.pop("category"))
                notes.append(f"'{s['merchant']}' is not a category, so it is searched as a merchant/description")
            else:
                s["category"] = c
        if op == "top_transactions":
            s["limit"] = count or s.get("limit") or 5
        if op == "compare_periods":
            periods = topic.get("periods") or ([topic["period"]] if topic.get("period") else [])
            if follow and len(periods) >= 2 and not explicit_period(question):
                a, b = sorted(periods[-2:], key=lambda p: _abs_month(p) or p, reverse=True)
                s["period"], s["period2"] = a, b
            if "period" not in s or s.get("period") == s.get("period2"):
                s["period"] = periods[-1] if periods else "last_month"
            if "period2" not in s or s["period2"] == s["period"]:
                prev = [p for p in periods if p != s["period"]]
                pm = _abs_month(s["period"])
                s["period2"] = prev[-1] if prev else (_month(pm, 1) if pm and re.fullmatch(r"\d{4}-\d{2}", pm) else "last_month")
        if op == "reduce_spending":
            s["percent"] = float(pct.group(1)) if pct else s.get("percent")
            if not s.get("percent"):
                return [], ["clarify:By what percentage would you like to reduce it?"]
        if op in ("affordability", "emi", "what_if"):
            if asked:
                if s.get("amount") is None or all(abs(float(s["amount"]) - a) > 0.01 * a for a in asked):
                    if s.get("amount") is not None:
                        notes.append(f"amount {s['amount']:g} replaced by the amount in your message ({asked[0]:g})")
                    s["amount"] = asked[0]
            elif op in ("affordability", "emi") or s.get("what_if_kind") in WHAT_IF_KINDS:
                if s.get("amount") is not None:
                    notes.append(f"amount {s['amount']:g} was not in your message")
                    s.pop("amount")
                if op == "affordability":
                    return [], ["clarify:What is the price of what you'd like to buy?"]
        if op == "emi":
            rate = re.search(r"(\d+(?:\.\d+)?)\s*%", question)
            ten = re.search(r"\b(\d+)\s*(years?|yrs?|months?)\b", question, re.I)
            if rate:
                s["rate"] = float(rate.group(1))
            if ten:
                s["tenure_months"] = int(ten.group(1)) * (12 if ten.group(2).lower().startswith("y") else 1)
        if op == "pause_investing":
            mv = months.group(1) if months else None
            s["months"] = (int(mv) if mv and mv.isdigit() else NUMBER_WORDS.get(mv, 12 if mv == "twelve" else None)) or s.get("months") or 6
        if op in SPEND_OPS | {"income_total", "savings"} and s.get("period") and not _valid_period(s["period"]) and follow \
                and topic.get("period") and not explicit_period(question):
            s["period"] = topic["period"]
        if op in SPEND_OPS | {"income_total", "savings"} and s.get("period") and not _valid_period(s["period"]):
            notes.append(f"period '{s['period']}' is not understood")
            return [], [f"clarify:Which period do you mean, for example last month or {_month(date.today().strftime('%Y-%m'), 2)}?"]
        if op == "debts" and re.search(r"\bEMIs?\b|\binstal+ments?\b", question, re.I):
            s["_asks_emi"] = True
        if op in ("debts", "balances") and re.search(r"\bprincipal\b|\boriginal(ly)? (loan|amount|borrow)", question, re.I):
            s["_asks_principal"] = True
        steps.append(s)
    uniq = []
    for x in steps:                                      # identical steps (e.g. two totals both turned into the same comparison) run once
        if x not in uniq:
            uniq.append(x)
    steps = uniq
    tots = [s for s in steps if s["op"] == "spend_total"]
    if len(tots) == 2 and re.search(r"\b(compare|comparison|vs\.?|versus|than|higher|lower|more|less|difference|change)\b", question, re.I) and \
            all(tots[0].get(k) == tots[1].get(k) for k in ("category", "merchant")) and \
            _abs_month(tots[0].get("period")) != _abs_month(tots[1].get("period")):
        a, b = sorted([tots[0].get("period") or "last_month", tots[1].get("period") or "last_month"], key=lambda p: _abs_month(p) or p, reverse=True)
        merged = {"op": "compare_periods", **{k: tots[0][k] for k in ("category", "merchant") if tots[0].get(k)}, "period": a, "period2": b}
        steps = [merged] + [s for s in steps if s["op"] != "spend_total"]
        notes.append("two totals for different periods were asked as a comparison")
    if _bare_reference(question, known if known is not None else state):
        return [], ["clarify:What would you like me to look at? For example, dining last month."]
    # a total the user did not ask for, next to the individual transactions they did ask for, is dropped (it puts merchant
    # totals beside transactions)
    tt = [s for s in steps if s["op"] == "top_transactions"]
    if tt and not re.search(r"\b(total|how much|in all|overall|altogether|sum)\b", question, re.I):
        same = lambda a, b: all(_abs_month(a.get(k)) == _abs_month(b.get(k)) if k == "period" else a.get(k) == b.get(k)
                                for k in ("category", "merchant", "period"))
        kept = [s for s in steps if not (s["op"] == "spend_total" and any(same(s, t) for t in tt))]
        if len(kept) < len(steps):
            notes.append("dropped a total that was not asked for")
            steps = kept
    # a follow-up that depends on a topic we do not have, and that does not itself say what or when: ask, don't guess
    if follow and not topic and not explicit_period(question) and not category_in(question) and any(
            s["op"] in {"top_transactions", "compare_periods", "reduce_spending"} and not (s.get("period") or s.get("category") or s.get("merchant"))
            for s in steps):
        return [], ["clarify:Which spending do you mean? For example, dining last month."]
    return steps, notes


COVERAGE = [  # unmistakable signals only; the planner decides everything else
    (r"\b(unusual|suspicious|fraud\w*|anomal\w*|odd transactions?)\b", "anomalies"),
    (r"\bnet worth\b", "net_worth"),
    (r"\bcredit risk\b|\bdefault risk\b", "credit_risk"),
    (r"\bforecast\b", "forecast"),
    (r"\bafford\b", "affordability"),
    (r"\btax regime\b|\bincome tax\b", "tax"),
    (r"\binsurance\b|\binsured\b", "insurance"),
    (r"\bretire\w*\b|\bFIRE\b", "retirement"),
    (r"\bhealth score\b|\bdiscipline\b", "health_score"),
    (r"\bmy EMIs?\b|\bEMIs? (do|did) I\b|\bpay\w* in EMIs?\b|\bmonthly EMIs?\b", "debts"),
    (r"\bmy SIPs?\b|\bSIPs? (do|did) I\b", "investments"),
]


def _valid_period(p: str) -> bool:
    return p in tools.PERIODS or bool(re.fullmatch(r"\d{4}(-\d{2})?", str(p)))


def _refers_back(q: str) -> bool:
    return bool(re.search(r"\b(that|those|these|them|it|this (spending|amount|month|one)|the same|both|the two|what about|and the|"
                          r"compare (it|that|them|both)|the (largest|biggest) one|which one|the one|top (one|two|three|\d))\b", q, re.I))


# ---------------------------------------------------------------- execution
def _calls(s: dict) -> list[tuple[str, dict]]:
    op, per = s["op"], s.get("period")
    f = {k: s[k] for k in ("category", "merchant") if s.get(k)}
    return {
        "spend_total": [("spending", {"period": per or "last_month", **f})],
        "spend_by_category": [("spending", {"period": per or "last_3_months"})],
        "top_transactions": [("transactions", {"period": per or "last_3_months", "limit": s.get("limit", 5), **f})],
        "compare_periods": [("spending", {"period": s.get("period"), **f}), ("spending", {"period": s.get("period2"), **f})],
        "spending_changes": [("compare_months", {k: v for k, v in (("month", _abs_month(per)), ("previous", _abs_month(s.get("period2")))) if v})],
        "reduce_spending": [("spending", {"period": per or "last_month", **f})],
        "income_total": [("income", {"period": per or "last_month"})],
        "savings": [("income", {"period": per or "last_month"}), ("spending", {"period": per or "last_month"})],
        "balances": [("accounts_and_balances", {})], "net_worth": [("net_worth", {})],
        "overview": [("profile_summary", {}), ("cash_flow", {})], "debts": [("debts_and_payoff", {})],
        "credit_cards": [("credit_cards", {})], "credit_risk": [("credit_risk", {})], "anomalies": [("anomaly_scan", {})],
        "forecast": [("cash_flow_forecast", {})], "peers": [("peer_benchmark", {})], "category_suggestions": [("category_suggestions", {})],
        "investments": [("investments", {})], "pause_investing": [("investments", {}), ("fire_forecast", {})],
        "goals": [("goals", {})], "retirement": [("fire_forecast", {})], "runway": [("runway", {})], "tax": [("tax_comparison", {})],
        "insurance": [("insurance", {})],
        "affordability": [("affordability", {"price": s.get("amount"), "item_type": _item_type(s.get("item")), "item_name": s.get("item")})],
        "what_if": [("plan_what_if", {"kind": s.get("what_if_kind") or "sip", "amount": s.get("amount"), "category": s.get("category")})],
        "plan": [("finora_plan", {})], "health_score": [("health_score", {})],
        "emi": [("emi_calculator", {"principal": s.get("amount"), "interest_rate": s.get("rate"), "tenure_months": s.get("tenure_months")})], "model_info": [("model_info", {"model": s.get("model")})],
    }.get(op, [])


def _item_type(item: str | None) -> str:
    i = str(item or "").lower()
    for k, words in {"car": ["car", "suv"], "bike": ["bike", "scooter", "motorcycle"], "home": ["home", "house", "flat", "apartment"],
                     "phone": ["phone", "iphone"], "gadget": ["laptop", "tv", "gadget", "camera"], "trip": ["holiday", "trip", "vacation", "travel"],
                     "education": ["course", "education", "mba", "college"], "wedding": ["wedding", "marriage"]}.items():
        if any(w in i for w in words):
            return k
    return "other"


def execute(ctx: dict, steps: list[dict]) -> list[dict]:
    """Runs every step's tools (in parallel: all are read-only on the same profile context) and adds derived figures."""
    jobs = [(i, name, args) for i, s in enumerate(steps) for name, args in _calls(s)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        outs = list(pool.map(lambda j: tools.call(j[1], ctx, {k: v for k, v in j[2].items() if v is not None}), jobs))
    by_step: dict[int, list] = {}
    for (i, name, args), out in zip(jobs, outs):
        by_step.setdefault(i, []).append({"tool": name, "arguments": {k: v for k, v in args.items() if v is not None}, "result": out})
    res = []
    for i, s in enumerate(steps):
        calls = by_step.get(i, [])
        res.append({"step": s, "calls": calls, "derived": _derive(s, calls)})
    # cross-step: is a transaction that was just looked up among the scanner's flags?
    items = [it for r in res if r["step"]["op"] == "top_transactions" for c in r["calls"] for it in (c["result"] or {}).get("items", [])]
    for r in res:
        cat = r["step"].get("category")
        if r["step"]["op"] == "anomalies" and cat and r["calls"] and not items:
            flagged = (r["calls"][0]["result"] or {}).get("flagged", [])
            mine = [f for f in flagged if str(f.get("category", "")).lower() == cat.lower()]
            by_cat: dict = {}
            for f in flagged:
                by_cat[f.get("category") or "Other"] = by_cat.get(f.get("category") or "Other", 0) + 1
            r["derived"] = {"category_asked_about": cat, "flagged_in_this_category": mine, "flagged_count_by_category": by_cat,
                            "note": (f"{len(mine)} of the {len(flagged)} flagged transactions are {cat}." if mine else
                                     f"None of the {len(flagged)} flagged transactions is {cat}.")}
    for r in res:
        if r["step"]["op"] == "anomalies" and items and r["calls"]:
            flagged = (r["calls"][0]["result"] or {}).get("flagged", [])
            r["derived"] = {"looked_up_transactions_flagged": [
                {"merchant": it["merchant"], "date": it["date"], "amount": it["amount"],
                 "flagged_as_unusual": any(f.get("date") == it["date"] and abs((f.get("amount") or 0) - it["amount"]) < 1 for f in flagged)}
                for it in items]}
    return res


def _derive(s: dict, calls: list[dict]) -> dict:
    op = s["op"]
    r = [c["result"] for c in calls]
    try:
        if op == "compare_periods" and all("total_spent" in x for x in r):
            a, b = r[0]["total_spent"], r[1]["total_spent"]
            out = {"period": r[0]["period"], "spent": a, "earlier_period": r[1]["period"], "earlier_spent": b,
                   "difference": round(a - b, 2), "change_pct": round((a - b) / b * 100, 1) if b else None,
                   "direction": "more" if a > b else "less" if a < b else "the same"}
            empty = [x["period"] for x in r[:2] if _no_data(x)]
            if empty:
                out["note"] = (f"No data is recorded for {', '.join(empty)} (Finora's data covers {r[0].get('data_covers')}), so this is not a "
                               "real change in spending: say so instead of calling it a decrease or increase.")
                out["change_pct"] = None
                out["direction"] = "not comparable (no data for one period)"
            return out
        if op == "reduce_spending" and "total_spent" in r[0]:
            months = max(1, len(r[0].get("months") or [1]))
            monthly = r[0]["total_spent"] / months
            cut = s["percent"] / 100
            return {"base_period": r[0]["period"], "base_spent": r[0]["total_spent"], "monthly_average": round(monthly, 2),
                    "percent": s["percent"], "saving_per_month": round(monthly * cut, 2), "saving_per_year": round(monthly * cut * 12, 2),
                    "note": "A what-if estimate from your actual spending, not something that has happened."}
        if op == "savings" and "total_income" in r[0] and "total_spent" in r[1]:
            return {"period": r[1]["period"], "income": r[0]["total_income"], "spent": r[1]["total_spent"],
                    "saved": round(r[0]["total_income"] - r[1]["total_spent"], 2),
                    "savings_rate_pct": round((r[0]["total_income"] - r[1]["total_spent"]) / r[0]["total_income"] * 100, 1) if r[0]["total_income"] else None}
        if op == "balances" and isinstance(r[0].get("bank_accounts"), list) and r[0]["bank_accounts"]:
            ranked = sorted(r[0]["bank_accounts"], key=lambda a: -(a.get("balance") or 0))   # ranking done here, not by the model
            out = {"bank_accounts_highest_first": ranked, "highest_balance_account": ranked[0], "lowest_balance_account": ranked[-1],
                   "total_bank_balance": r[0].get("total_bank_balance")}
            cards = [c for c in r[0].get("credit_cards") or [] if c.get("outstanding") is not None]
            if cards:
                out["card_with_highest_outstanding"] = max(cards, key=lambda c: c["outstanding"])
            return out
        if op == "pause_investing":
            inv, fire = r[0], r[1]
            sip = float(inv.get("sip_monthly_total") or 0)
            n = int(s.get("months") or 6)
            rate = float((fire.get("inputs") or {}).get("nominal_return_pct") or 0) / 100
            age = (fire.get("inputs") or {}).get("age")
            target = fire.get("retirement_age_target")
            years = max(0, (target or 0) - (age or 0))
            fv = sum(sip * (1 + rate / 12) ** (years * 12 - k) for k in range(n)) if rate and years else None
            if sip == 0:
                return {"monthly_sip": 0.0, "months_paused": n, "contributions_skipped": 0.0, "has_active_sips": False,
                        "note": "You have no active SIPs (₹0 a month), so pausing would skip nothing. total_invested is past money "
                                "already invested, not a monthly contribution."}
            return {"monthly_sip": sip, "months_paused": n, "contributions_skipped": round(sip * n, 2),
                    "value_at_retirement_age_of_skipped_contributions": round(fv) if fv else None, "assumed_return_pct": rate * 100,
                    "retirement_age_target": target,
                    "note": "Estimate: skipped contributions grown at the plan's assumed return until the target retirement age."}
    except (KeyError, TypeError, ZeroDivisionError):
        return {}
    return {}


# ---------------------------------------------------------------- interpretation, requirements, checks
def _p(per: str | None) -> str:
    if not per:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}", per):
        return date(int(per[:4]), int(per[5:]), 1).strftime("%B %Y")
    return per.replace("_", " ")


def interpretation(steps: list[dict]) -> str:
    parts = []
    for s in steps:
        what = s.get("category") or (f"'{s['merchant']}'" if s.get("merchant") else None)
        op = s["op"]
        if op == "top_transactions":
            n = s.get("limit", 5)
            parts.append(f"the {'single largest' if n == 1 else f'{n} largest'} individual {what or 'spending'} transaction{'s' if n != 1 else ''} in {_p(s.get('period')) or 'the period'} (individual transactions, not merchant totals)")
        elif op == "compare_periods":
            parts.append(f"{what or 'total'} spending in {_p(s['period'])} compared with {_p(s['period2'])}")
        elif op == "spend_total":
            parts.append(f"{what or 'total'} spending in {_p(s.get('period')) or 'last month'}")
        elif op == "reduce_spending":
            parts.append(f"saving from cutting {what or 'total'} spending ({_p(s.get('period')) or 'last month'}) by {s['percent']:g}%")
        else:
            parts.append(OPS[op] + (f" ({_p(s.get('period'))})" if s.get("period") else ""))
    return "; ".join(parts)


def requirements(results: list[dict]) -> list[tuple[str, float]]:
    """Figures the answer MUST contain for it to answer the question (semantic check)."""
    req = []
    for r in results:
        op, d = r["step"]["op"], r["derived"]
        res = [c["result"] for c in r["calls"]]
        if not res or any("error" in x for x in res):
            continue
        x = res[0]
        if op == "spend_total":
            req.append(("total", x.get("total_spent", x.get("money_moved_not_spending"))))
        elif op == "top_transactions":
            req += [(f"item {i + 1}", it["amount"]) for i, it in enumerate(x.get("items", []))]
        elif op == "compare_periods" and d:
            req += [("spent", d["spent"]), ("earlier", d["earlier_spent"])]
        elif op == "reduce_spending" and d:
            req.append(("saving per month", d["saving_per_month"]))
        elif op == "savings" and d:
            req.append(("saved", d["saved"]))
        elif op == "income_total":
            req.append(("income", x.get("total_income")))
        elif op == "net_worth":
            req.append(("net worth", x.get("net_worth")))
        elif op == "balances":
            req.append(("bank total or largest account", [x.get("total_bank_balance")] + [a.get("balance") for a in x.get("bank_accounts", [])]))
        elif op == "credit_risk" and x.get("available") is not False:
            req.append(("default probability", x.get("overall_default_probability_pct")))
        elif op == "credit_cards" and x.get("total_outstanding") is not None:
            req.append(("total card outstanding", [x["total_outstanding"]] + [c.get("outstanding") for c in x.get("cards", [])][:1]
                        if len(x.get("cards", [])) == 1 else x["total_outstanding"]))
        elif op == "forecast" and x.get("available") is not False:
            req += [("forecast", x.get("predicted_total_expense")), ("baseline", x.get("baseline_three_month_average"))]
        elif op == "pause_investing" and d:
            req.append(("skipped contributions", d.get("contributions_skipped")))
        elif op == "debts":
            req.append(("monthly EMI", x.get("total_emi")) if r["step"].get("_asks_emi") else ("total debt", x.get("total_debt")))
        if op in ("debts", "balances") and r["step"].get("_asks_principal") and x.get("loans"):
            req.append(("original loan principal", [l.get("original_principal") for l in x["loans"] if l.get("original_principal")]))
    # zero stays required: a true ₹0 must be stated (as ₹0 or 'no ...'), not replaced by some other figure from the results
    return [(k, v) for k, v in req if v not in (None, [])]


def _is_zero(v) -> bool:
    vals = v if isinstance(v, list) else [v]
    return any(isinstance(x, (int, float)) and float(x) == 0 for x in vals)


def _says_none(text: str) -> bool:
    return bool(re.search(r"\b(no|none|nil|zero|not any|don'?t have any|do not have any|haven'?t any)\b", text, re.I))


def _has(text: str, v, money=True) -> bool:
    vals = v if isinstance(v, list) else [v]
    nums = []                                               # (value, tolerance from the precision the text shows)
    for m in guard._NUM.finditer(text):
        try:
            raw = m.group(2).replace(",", "")
            mult = guard._MULT.get((m.group(3) or "").lower(), 1)
            dec = len(raw.split(".")[1]) if "." in raw else 0
            nums.append((float(raw) * mult, 0.5 * 10 ** -dec * mult if mult > 1 else 0.0))
        except ValueError:
            pass
    for want in vals:
        if want is None:
            continue
        w = abs(float(want))
        if any(abs(n - w) <= max(1.0, 0.006 * w, tol) for n, tol in nums):
            return True
    return False


def _currency_split(results: list[dict]) -> tuple[dict, dict]:
    inr, gbp = {}, {}
    for i, r in enumerate(results):
        for c in r["calls"]:
            res = c["result"]
            if isinstance(res, dict):
                g = {k: v for k, v in res.items() if k in ("measured_error",)}
                gbp[f"gbp:{i}:{c['tool']}"] = g
                inr[f"inr:{i}:{c['tool']}"] = {k: v for k, v in res.items() if k not in g}
        inr[f"inr:{i}:derived"] = r["derived"]
    return inr, gbp


def check(text: str, results: list[dict], question: str, steps: list[dict]) -> dict:
    """Numbers only from THIS turn's results/question; ₹ figures must be INR facts and £ figures GBP facts; required figures
    present; the requested number of items respected."""
    inr, gbp = _currency_split(results)
    num = guard.verify(text, {**inr, **gbp}, question)
    problems = list(num["unsupported"])
    gbp_nums = guard.collect_numbers(gbp)
    inr_nums = guard.collect_numbers(inr) | guard.collect_numbers(question)
    for m in re.finditer(r"₹\s?(\d[\d,]*(?:\.\d+)?)\s*(L|Cr|lakh|crore)?", text):
        v = float(m.group(1).replace(",", "")) * {"l": 1e5, "lakh": 1e5, "cr": 1e7, "crore": 1e7}.get((m.group(2) or "").lower(), 1)
        if any(abs(v - g) <= 1 for g in gbp_nums) and not any(abs(v - n) <= max(1, 0.006 * n) for n in inr_nums):
            problems.append(f"{m.group(0)} is a GBP figure written as rupees")
    missing = [k for k, v in requirements(results) if not (_has(text, v) or (_is_zero(v) and _says_none(text)))]
    for s, r in zip(steps, results):
        if s["op"] == "top_transactions":
            items = (r["calls"][0]["result"] or {}).get("items", []) if r["calls"] else []
            listed = [x for x in re.findall(r"₹\s?\d[\d,]*(?:\.\d+)?", text)]
            if items and len(listed) > len(items) + 2:          # allow a total/average besides the items
                problems.append(f"lists {len(listed)} amounts for {len(items)} requested items")
        if s["op"] == "anomalies" and "category_asked_about" in (r.get("derived") or {}):
            d = r["derived"]
            others = [f for f in ((r["calls"][0]["result"] or {}).get("flagged") or []) if f not in d["flagged_in_this_category"]]
            if any(_has(text, f.get("amount")) for f in others if f.get("amount")):
                problems.append(f"lists flagged transactions outside {d['category_asked_about']}")
            for f in d["flagged_in_this_category"]:
                if not _has(text, f.get("amount")):
                    missing.append(f"the flagged {d['category_asked_about']} transaction {f.get('merchant')}")
            cat = d["category_asked_about"]
            if d["flagged_in_this_category"] and re.search(rf"\b(none|no|not any)\b[^.\n]*\bflagged\b[^.\n]*\b{re.escape(cat)}\b|"
                                                           rf"\b(none|no)\b[^.\n]*\b{re.escape(cat)}\b[^.\n]*\bflagged\b", text, re.I):
                problems.append(f"says no {cat} transaction is flagged, but {len(d['flagged_in_this_category'])} is")
            words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            for m_ in re.finditer(r"\b(\d+|one|two|three|four|five)\s+(?:out of \d+\s+)?(?:[\w-]+\s+){0,4}?(?:in|for)\s+(?:the\s+)?([A-Z][a-z]+)", text):
                n_ = int(m_.group(1)) if m_.group(1).isdigit() else words[m_.group(1).lower()]
                c_ = m_.group(2)
                if c_ in d["flagged_count_by_category"] and d["flagged_count_by_category"][c_] != n_:
                    problems.append(f"says {n_} flagged in {c_}; the scanner flagged {d['flagged_count_by_category'][c_]}")
        if s["op"] == "forecast" and re.search(r"\bleft( over)?\b|\bsurplus\b|\bremain\w*\b|\bspare\b|\bshort(fall)?\b|\bdeficit\b", question, re.I):
            fc = next((c_["result"] for c_ in r["calls"] if c_["tool"] == "cash_flow_forecast"), {}) or {}
            if fc.get("projected_surplus") is not None and not _has(text, fc["projected_surplus"]):
                missing.append("the projected amount left over (projected_surplus)")
        if s["op"] == "pause_investing" and (r.get("derived") or {}).get("has_active_sips") is False and \
                not re.search(r"\bno (active )?SIPs?\b|don'?t have (any )?(active )?SIPs?|₹\s?0\b", text, re.I):
            missing.append("that there are no active SIPs (₹0 a month)")
        if s["op"] == "balances" and r.get("derived") and not re.search(r"\b(highest|most|largest|biggest|max|lowest|least|smallest|min)", question, re.I):
            accts = r["derived"]["bank_accounts_highest_first"]
            named_acct = [a for a in accts if (a.get("bank") or "").split()[0].lower() in question.lower()]
            want = named_acct[0]["balance"] if len(named_acct) == 1 else r["derived"]["total_bank_balance"]
            if not _has(text, want):
                missing.append("the balance asked for" + (f" ({named_acct[0]['bank']})" if len(named_acct) == 1 else " (the total across bank accounts)"))
        if s["op"] == "balances" and r.get("derived"):           # "which account has the most/least" -> that account, by name and amount
            pick = ("highest_balance_account" if re.search(r"\b(highest|most|largest|biggest|max)", question, re.I) else
                    "lowest_balance_account" if re.search(r"\b(lowest|least|smallest|min)", question, re.I) else None)
            if pick:
                a = r["derived"][pick]
                if not _has(text, a.get("balance")) or (a.get("bank") or "").split()[0].lower() not in text.lower():
                    missing.append(f"the {pick.replace('_', ' ')} ({a.get('bank')} {a.get('account')})")
        if s.get("merchant") and s["op"] in SPEND_OPS and s["merchant"].split()[0].lower() not in text.lower():
            missing.append(f"the merchant {s['merchant']}")
        if s.get("category") and s["op"] in SPEND_OPS and s["category"].lower() not in text.lower() and \
                not (s["category"] == "Dining" and re.search(r"\b(food|eating|restaurant)", text, re.I)):
            missing.append(f"the category {s['category']}")
    if re.search(r"\bThe question means\b|\bRESULTS\b|\bderived\b|\bflagged_in_|_count\b|total_spent|months_without_data", text):
        problems.append("echoes internal instructions or field names instead of answering")
    if ACTION_CLAIM.search(text):
        problems.append("claims to have changed data; the AI CFO cannot change anything")
    return {"ok": not problems and not missing, "unsupported": problems, "missing": missing, "checked": num["checked"]}


ACTION_CLAIM = re.compile(r"\b(I|I've|I have|we have|we've)\s+(now\s+|just\s+)?(deleted|removed|transferred|moved|cancel+ed|updated|changed|paid|"
                          r"sent|erased|recategori[sz]ed|edited)\b|\b(have|has) (now )?been (deleted|removed|erased|cancel+ed|updated|changed|"
                          r"recategori[sz]ed|transferred|wiped)\b", re.I)
ACTION_REQUEST = re.compile(r"^\s*(please\s+|can you\s+|could you\s+|go ahead and\s+)?(delete|remove|erase|wipe|clear|transfer|send|move|cancel|"
                            r"close|edit|update|rename|recategori[sz]e|change|reset|undo)\s+(my|all|the|this|that|these|those|it|them|every|₹|rs\.?|\d)", re.I)


# ---------------------------------------------------------------- deterministic fallback answers
def template(results: list[dict]) -> str:
    from .writer import WRITERS, inr
    out = []
    for r in results:
        op, d = r["step"]["op"], r["derived"]
        res = [c["result"] for c in r["calls"]]
        if any(isinstance(x, dict) and x.get("error") for x in res):
            out.append("I couldn't get that: " + "; ".join(x["error"] for x in res if isinstance(x, dict) and x.get("error")))
            continue
        if op == "top_transactions" and res:
            items = res[0].get("items", [])
            what = res[0].get("category") or res[0].get("merchant") or "spending"
            if not items:
                out.append(f"No {what} transactions in {res[0]['period']}.")
            else:
                lines = [f"{i + 1}. {it['merchant']}: {inr(it['amount'])} on {it['date']}" for i, it in enumerate(items)]
                out.append(f"Largest {what} transaction{'s' if len(items) > 1 else ''} in {res[0]['period']}:\n" + "\n".join(lines))
        elif op == "balances" and d:
            accts = "; ".join(f"{a['bank']} {a['type']} {a['account']}: {inr(a['balance'])}" for a in d["bank_accounts_highest_first"])
            out.append(f"Bank balances, highest first: {accts}. Total across bank accounts: {inr(d['total_bank_balance'])}.")
        elif op == "compare_periods" and d and d.get("change_pct") is None and "not comparable" in str(d.get("direction")):
            what = r["step"].get("category") or r["step"].get("merchant") or "total"
            out.append(f"{what} spending: {d['period']} {inr(d['spent'])}, {d['earlier_period']} {inr(d['earlier_spent'])}. "
                       + d["note"].split(", so")[0] + ", so the two periods can't be compared as a real change.")
        elif op == "compare_periods" and d:
            out.append(f"{d['period']}: {inr(d['spent'])}; {d['earlier_period']}: {inr(d['earlier_spent'])}. That is "
                       f"{inr(abs(d['difference']))} {d['direction']}" + (f" ({d['change_pct']:+}%)." if d.get("change_pct") is not None else "."))
        elif op == "reduce_spending" and d:
            out.append(f"Cutting {d['percent']:g}% from your average of {inr(d['monthly_average'])} a month ({d['base_period']}) would save about "
                       f"{inr(d['saving_per_month'])} a month, {inr(d['saving_per_year'])} a year. {d['note']}")
        elif op == "savings" and d:
            out.append(f"In {d['period']} you earned {inr(d['income'])} and spent {inr(d['spent'])}, so you saved {inr(d['saved'])}"
                       + (f" ({d['savings_rate_pct']}% of income)." if d.get("savings_rate_pct") is not None else "."))
        elif op == "anomalies" and d and "category_asked_about" in d:
            cat, mine = d["category_asked_about"], d["flagged_in_this_category"]
            lim = (res[0] or {}).get("limitation") or ""
            if mine:
                def why(f, cat=cat):
                    bits = []
                    if f.get("times_typical"):
                        bits.append(f"{f['times_typical']}× your typical {cat} amount"
                                    + (f" of {inr(f['typical_amount'])}" if f.get("typical_amount") else ""))
                    rs = f.get("reasons")
                    bits += [str(x) for x in (rs if isinstance(rs, list) else [rs] if rs else [])][:2]
                    return f" ({'; '.join(bits)})" if bits else ""
                out.append(f"{len(mine)} {cat} transaction{'s are' if len(mine) > 1 else ' is'} flagged as unusual for you: "
                           + "; ".join(f"{f.get('merchant')} {inr(f.get('amount'))} on {f.get('date')}{why(f)}" for f in mine)
                           + f". {d['note']} {lim}")
            else:
                out.append(f"None of your {cat} transactions is flagged as unusual. {lim}")
        elif op == "pause_investing" and d and d.get("has_active_sips") is False:
            out.append(d["note"])
        elif op == "pause_investing" and d:
            out.append(f"Pausing your {inr(d['monthly_sip'])} monthly SIPs for {d['months_paused']} months skips {inr(d['contributions_skipped'])} of "
                       f"contributions" + (f", worth about {inr(d['value_at_retirement_age_of_skipped_contributions'])} by age {d['retirement_age_target']} "
                                           f"at {d['assumed_return_pct']:g}% a year" if d.get("value_at_retirement_age_of_skipped_contributions") else "")
                       + ". " + d["note"])
        elif op == "health_score" and res:
            h = res[0]
            out.append(f"Your Financial Health Score is {h['score']} ({h['band']}). Pillars: " + ", ".join(f"{k} {v}" for k, v in (h.get("pillars") or {}).items()) + ". " + h["note"])
        elif op == "model_info" and res:
            out.append("; ".join(f"{m['model']}: {m['status']}" + (f". {m['limitations']}" if m.get("limitations") else "") for m in res[0].get("models", [])))
        else:
            for c in r["calls"]:
                w = WRITERS.get(c["tool"])
                if w:
                    try:
                        out.append(w(c["result"]))
                    except Exception:
                        pass
    return "\n\n".join(x for x in out if x) or "I couldn't compute that from your data."


# ---------------------------------------------------------------- conversation state
def _no_data(res: dict) -> bool:
    """A spending result for a period with no recorded data at all (not 'spent nothing')."""
    return bool(res) and not res.get("transactions") and bool(res.get("months_without_data")) and \
        len(res.get("months_without_data") or []) >= len(res.get("months") or [1])


def new_state(old: dict, steps: list[dict], results: list[dict]) -> dict:
    st = {"topic": dict(old.get("topic") or {}), "log": list(old.get("log") or [])[-19:], "turns": int(old.get("turns") or 0) + 1}
    for s, r in zip(steps, results):
        if s["op"] in SPEND_OPS:
            res0 = r["calls"][0]["result"] if r["calls"] else {}
            per = _abs_month(s.get("period")) or (res0 or {}).get("period")     # store an absolute month so follow-ups compare like with like
            t = st["topic"] if st["topic"].get("category") == s.get("category") and st["topic"].get("merchant") == s.get("merchant") else {}
            periods = [p for p in (t.get("periods") or []) if p]
            for p in ([_abs_month(s["period2"]), _abs_month(s["period"])] if s["op"] == "compare_periods" else [per]):
                if p and p not in periods:
                    periods.append(p)
            if s["op"] == "compare_periods" and len(r["calls"]) == 2:
                # follow-ups after a comparison refer to the spending discussed: prefer the compared month that has data
                later, earlier = (c_["result"] or {} for c_ in r["calls"])
                if _no_data(later) and not _no_data(earlier):
                    per = _abs_month(s.get("period2")) or earlier.get("period")
            st["topic"] = {"op": s["op"], "category": s.get("category"), "merchant": s.get("merchant"), "period": per,
                           "periods": periods[-3:]}
        elif s["op"] in ("income_total", "savings"):
            st["topic"] = {"op": s["op"], "period": s.get("period")}
        else:                                           # e.g. anomalies/forecast: keep the spending subject for later follow-ups
            st["topic"] = {**{k: v for k, v in st["topic"].items() if k in ("category", "merchant", "period", "periods")}, "op": s["op"]}
        st["log"].append(summary_line(s, r))
    st["log"] = [x for x in st["log"] if x][-20:]
    return st


def summary_line(s: dict, r: dict) -> str:
    """One factual line from verified tool output (never from model prose)."""
    from .writer import inr
    d = r["derived"]
    res = [c["result"] for c in r["calls"]]
    if not res or any(isinstance(x, dict) and x.get("error") for x in res):
        return ""
    x = res[0]
    what = s.get("category") or s.get("merchant") or "total"
    op = s["op"]
    if op == "spend_total":
        return f"{what} spending {x['period']}: {inr(x.get('total_spent', x.get('money_moved_not_spending', 0)))}"
    if op == "top_transactions":
        return f"largest {what} transactions {x['period']}: " + ", ".join(f"{i['merchant']} {inr(i['amount'])} ({i['date']})" for i in x.get("items", []))
    if op == "compare_periods" and d:
        return f"{what} spending {d['period']} {inr(d['spent'])} vs {d['earlier_period']} {inr(d['earlier_spent'])}"
    if op == "reduce_spending" and d:
        return f"cutting {what} by {d['percent']:g}% saves {inr(d['saving_per_month'])}/month"
    if op == "net_worth":
        return f"net worth {inr(x.get('net_worth'))}"
    if op == "income_total":
        return f"income {x.get('period')}: {inr(x.get('total_income'))}"
    if op == "savings" and d:
        return f"saved {d['period']}: {inr(d['saved'])}"
    if op == "anomalies" and d and "category_asked_about" in d:
        mine = d["flagged_in_this_category"]
        return (f"unusual {d['category_asked_about']} transactions: " + ", ".join(f"{f.get('merchant')} {inr(f.get('amount'))} ({f.get('date')})" for f in mine)
                if mine else f"no {d['category_asked_about']} transaction flagged as unusual")
    if op == "anomalies":
        return f"unusual-transaction scan: {x.get('flagged_count', 0)} flagged"
    return op.replace("_", " ") + " looked up"


SUMMARY_REQUEST = re.compile(r"\b(summari[sz]e|recap|sum up|summary)\b[^?]*\b(discuss\w*|talk\w*|conversation|so far|covered|chat)\b|"
                             r"\bwhat (have |did )?we (discuss|cover|talk)\w*", re.I)


def conversation_summary(state: dict) -> str:
    """'Summarise what we discussed': built only from the verified facts logged in this conversation (no model prose)."""
    log = [x for x in (state.get("log") or []) if x and not x.endswith("looked up")]
    if not log:
        return "We haven't looked up any of your figures in this conversation yet, so there is nothing of yours to summarise."
    seen, lines = set(), []
    for x in log[-12:]:
        if x not in seen:
            seen.add(x)
            lines.append(f"- {x[0].upper()}{x[1:]}")
    return "Here is what we covered, using the figures Finora looked up in this conversation:\n" + "\n".join(lines)

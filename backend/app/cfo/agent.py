"""The AI CFO - Finora's finance assistant.

Pipeline for every question:
  1. ROUTE    recognise the intent with rules and run the matching calculator tool(s)
              (no model involved, so the right numbers are always computed);
  2. TOOL-CALL if nothing matched and a model is available, let the model choose tools
              (Ollama native tool-calling, max 2 rounds, arguments validated);
  3. EXPLAIN  ask the model to explain the tool results in plain language;
  4. VERIFY   check every number in the model's answer against the tool results;
              if any number is unsupported, discard the model text and use the rule-based answer.
If no model is running, steps 2-4 are skipped and the rule-based writer answers.
"""
from __future__ import annotations

import json
import re

from . import guard, llm, router, tools, writer

SYSTEM = """You are Finora's AI CFO, a personal finance assistant for an Indian user.
STRICT RULES:
- Use ONLY the numbers given in the DATA block. Never calculate, estimate or invent a number.
- If the data does not contain something, say you do not have it.
- Amounts are Indian rupees. Write them like ₹45,000 or ₹12.5 L or ₹1.2 Cr exactly as their values in DATA.
- Be direct and practical: answer the question first, then give the 1-2 most important reasons and one clear next step.
- Maximum 130 words. Plain sentences, no markdown tables, no headings.
- Unusual transactions are not fraud. Forecasts are estimates, not guarantees.
- You give educational guidance, not licensed financial advice. Do not recommend specific stocks or funds to buy."""

OUT_OF_SCOPE = ("I'm Finora's finance assistant, so I can help with your cash flow, spending, investments, taxes, credit cards, "
                "debt, goals, big purchases and retirement planning. Try asking: \"Can I afford a ₹12 lakh car?\", "
                "\"When can I retire?\" or \"How long would my savings last?\"")


def _slim(facts, limit=2600):
    s = json.dumps(facts, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "…"


def _explain(question: str, results: list[tuple[str, dict]], history: list[dict]) -> str:
    data = {name: facts for name, facts in results}
    msgs = [{"role": "system", "content": SYSTEM}]
    msgs += [{"role": h["role"], "content": h["content"][:400]} for h in history[-4:]]
    msgs.append({"role": "user", "content": f"QUESTION: {question}\n\nDATA (the only numbers you may use):\n{_slim(data)}\n\n"
                                            "Answer the question using only DATA."})
    return (llm.chat(msgs, temperature=0.2, max_tokens=320).get("content") or "").strip()


def _model_tool_calls(question: str, ctx: dict) -> list[tuple[str, dict]]:
    msgs = [{"role": "system", "content": "You are a finance assistant. Call the tool(s) needed to answer the user's question about "
                                          "their own finances. If the question is not about personal finance, call no tool."},
            {"role": "user", "content": question}]
    msg = llm.chat(msgs, tools=tools.ollama_schema(), temperature=0.0, max_tokens=200)
    out = []
    for tc in (msg.get("tool_calls") or [])[:3]:
        fn = tc.get("function", {})
        name, args = fn.get("name"), fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name in tools.REGISTRY:
            out.append((name, args))
    return out


def answer(question: str, ctx: dict, history: list[dict] | None = None, use_llm: bool = True) -> dict:
    history = history or []
    question = (question or "").strip()
    if not question:
        return {"answer": "Ask me anything about your finances.", "engine": "rules", "tools_used": [], "verified": True}
    st = llm.status() if use_llm else {"available": False, "model": None}
    trace = {"routed_by": "rules", "llm": st.get("model") if st["available"] else None}

    concept_first = writer.glossary_answer(question)
    if concept_first and not re.search(r"\b(my|mine|i|me)\b", question.lower()):
        return {"answer": concept_first + "\n\n" + writer.DISCLAIMER, "engine": "rules", "tools_used": ["glossary"], "verified": True, "trace": trace}
    calls = router.route(question)
    if calls and calls[0][0] == "__ask__":
        return {"answer": calls[0][1]["question"], "engine": "rules", "tools_used": [], "verified": True, "trace": trace}
    if not calls:
        concept = writer.glossary_answer(question)
        if concept and not st["available"]:
            return {"answer": concept + "\n\n" + writer.DISCLAIMER, "engine": "rules", "tools_used": ["glossary"], "verified": True, "trace": trace}
        if st["available"]:
            try:
                calls = _model_tool_calls(question, ctx)
                trace["routed_by"] = "model tool-calling"
            except Exception as e:
                trace["tool_call_error"] = f"{type(e).__name__}"
        if not calls and concept:
            return {"answer": concept + "\n\n" + writer.DISCLAIMER, "engine": "rules", "tools_used": ["glossary"], "verified": True, "trace": trace}
        if not calls:
            if st["available"]:  # general finance concept question: let the model explain, with no personal numbers
                try:
                    txt = llm.chat([{"role": "system", "content": "You are a finance teacher for an Indian audience. Explain the concept in under 110 words. "
                                                                 "Do not state any figure about the user. If the question is not about money or finance, reply exactly: OUT_OF_SCOPE"},
                                    {"role": "user", "content": question}], temperature=0.3, max_tokens=260).get("content", "").strip()
                    if txt and "OUT_OF_SCOPE" not in txt:
                        return {"answer": txt + "\n\n" + writer.DISCLAIMER, "engine": st["model"], "tools_used": [], "verified": True,
                                "trace": {**trace, "mode": "concept explanation (no personal figures)"}}
                except Exception:
                    pass
            return {"answer": OUT_OF_SCOPE, "engine": "rules", "tools_used": [], "verified": True, "trace": trace}

    results = [(name, tools.call(name, ctx, args)) for name, args in calls]
    results = [(n, f) for n, f in results if "error" not in f] or results
    fallback = writer.write(results)
    out = {"tools_used": [n for n, _ in results], "facts": {n: f for n, f in results}, "trace": trace}
    if st["available"]:
        try:
            text = _explain(question, results, history)
            check = guard.verify(text, out["facts"], question)
            trace["number_check"] = check
            if text and check["ok"]:
                return {**out, "answer": text + "\n\n" + writer.DISCLAIMER, "engine": st["model"], "verified": True}
            trace["rejected_model_answer"] = text[:300]
        except Exception as e:
            trace["llm_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return {**out, "answer": fallback + "\n\n" + writer.DISCLAIMER, "engine": "rules", "verified": True}


def briefing(ctx: dict, use_llm: bool = True) -> dict:
    """Monthly CFO briefing: where you stand, what changed, what to fix."""
    a = ctx["analysis"]
    cf, nw, fire = a["cash_flow"], a["net_worth"], a["fire"]
    fc = a["ml"].get("forecast", {})
    facts = {
        "month": cf["latest_month"], "income": cf["monthly_income"], "expenses": cf["monthly_expenses"], "saved": cf["monthly_savings"],
        "savings_rate_pct": cf["savings_rate_pct"], "expense_change_pct_vs_previous_month": cf["expense_change_pct"],
        "net_worth": nw["net_worth"], "net_worth_change_12m": nw["change_over_period"], "health_score": a["health_score"]["score"],
        "runway_months": a["liquidity"]["runway_months"], "fire_progress_pct": fire["progress_pct"], "fire_age": fire["fire_age"],
        "next_month_predicted_spend": fc.get("predicted_total_expense"), "next_month_status": fc.get("projected_status"),
        "top_actions": [{"priority": r["priority"], "finding": r["finding"], "action": r["action"]} for r in a["recommendations"][:3]],
    }
    lines = []
    if facts["income"] is not None and facts["expenses"] is not None:
        lines.append(f"In {facts['month']} you earned {writer.inr(facts['income'])} and spent {writer.inr(facts['expenses'])}, "
                     + (f"saving {writer.inr(facts['saved'])} ({facts['savings_rate_pct']}%)." if (facts["saved"] or 0) >= 0 else f"a deficit of {writer.inr(-facts['saved'])}.")
                     + (f" Spending moved {facts['expense_change_pct_vs_previous_month']:+}% versus the previous month." if facts["expense_change_pct_vs_previous_month"] is not None else ""))
    elif facts["income"] is not None:
        lines.append(f"In {facts['month']} you recorded income of {writer.inr(facts['income'])}; spending is not known yet, so savings cannot be measured.")
    elif facts["expenses"] is not None:
        lines.append(f"In {facts['month']} you spent {writer.inr(facts['expenses'])}; income is not recorded, so savings cannot be measured.")
    else:
        lines.append("There is no income or spending history yet, so this briefing covers balances and holdings only.")
    lines.append(f"Net worth stands at {writer.inr(facts['net_worth'])}"
                 + (f" ({'up' if facts['net_worth_change_12m'] >= 0 else 'down'} {writer.inr(abs(facts['net_worth_change_12m']))} over 12 months)" if facts["net_worth_change_12m"] is not None else "")
                 + (f"; health score {facts['health_score']}/100" if facts["health_score"] is not None else "; health score not yet available")
                 + (f"; runway {facts['runway_months']} months." if facts["runway_months"] is not None else "."))
    if fire.get("available", True):
        lines.append(f"FIRE progress: {facts['fire_progress_pct']}% of your number" + (f", on course for age {facts['fire_age']}." if facts["fire_age"] else ", not reachable before 75 at the current pace."))
    else:
        lines.append("A FIRE projection needs your yearly expenses, which are not known yet.")
    if a.get("completeness", {}).get("missing"):
        lines.append("Still missing: " + ", ".join(a["completeness"]["missing"][:4]) + ".")
    if facts["next_month_predicted_spend"]:
        lines.append(f"Next month's spending is forecast at {writer.inr(facts['next_month_predicted_spend'])} - a projected {facts['next_month_status']}.")
    text = " ".join(lines)
    engine = "rules"
    st = llm.status() if use_llm else {"available": False}
    if st["available"]:
        try:
            msgs = [{"role": "system", "content": SYSTEM + "\nWrite a 4-sentence monthly briefing in a CFO's voice: position, what changed, biggest risk, the one action to take."},
                    {"role": "user", "content": f"DATA (the only numbers you may use):\n{_slim(facts)}"}]
            t = (llm.chat(msgs, temperature=0.3, max_tokens=300).get("content") or "").strip()
            if t and guard.verify(t, facts)["ok"]:
                text, engine = t, st["model"]
        except Exception:
            pass
    return {"month": facts["month"], "briefing": text, "engine": engine, "facts": facts,
            "priorities": facts["top_actions"], "alerts": a["alerts"], "disclaimer": writer.DISCLAIMER}

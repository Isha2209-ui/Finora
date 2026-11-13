"""Intent router - maps a question to calculator tools WITHOUT using the language model.

Common money questions are recognised by keywords and their numbers are parsed here,
so the right calculator always runs with the right inputs. The language model is then
only asked to explain the result. Open-ended questions fall through to model tool-calling.
"""
from __future__ import annotations

import re

_NUM = r"(\d+(?:[.,]\d+)*)"
_AMOUNT = re.compile(rf"(?:₹|rs\.?|inr)?\s*{_NUM}\s*(crores?|cr|lakhs?|lacs?|lac|l|k|thousand)?\b", re.I)
_UNIT = {"cr": 1e7, "crore": 1e7, "crores": 1e7, "l": 1e5, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
         "k": 1e3, "thousand": 1e3}


def parse_amounts(text: str) -> list[float]:
    """All rupee amounts in the text ("15L", "12 lakh", "₹8,00,000", "1.2 cr", "50k")."""
    out = []
    for m in _AMOUNT.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        nxt = text[m.end():m.end() + 12].lower()
        if not unit and (nxt.lstrip().startswith(("%", "percent", "year", "yr", "month", "mo")) or re.match(r"\s*-?\s*(year|yr|month)", nxt)):
            continue
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        val *= _UNIT.get(unit, 1)
        if unit or val >= 1000:
            out.append(val)
    return out


def parse_rate(text: str) -> float | None:
    m = re.search(rf"{_NUM}\s*(?:%|percent|per cent)", text, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def parse_tenure_months(text: str) -> int | None:
    m = re.search(rf"{_NUM}\s*-?\s*(years?|yrs?|months?|mos?)\b", text, re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(round(n * 12)) if m.group(2).lower().startswith("y") else int(round(n))


def parse_age(text: str) -> int | None:
    m = re.search(r"(?:at|by|age(?:\s+of)?)\s+(\d{2})\b", text, re.I)
    return int(m.group(1)) if m and 30 <= int(m.group(1)) <= 80 else None


ITEMS = {"car": ["car", "suv", "sedan", "hatchback", "creta", "swift", "nexon", "thar", "fortuner"],
         "bike": ["bike", "scooter", "motorcycle", "bullet", "activa"],
         "home": ["house", "home", "flat", "apartment", "property", "plot"],
         "phone": ["phone", "iphone", "mobile", "pixel", "samsung"],
         "gadget": ["laptop", "macbook", "tv", "camera", "playstation", "ps5", "ipad"],
         "trip": ["trip", "vacation", "holiday", "travel to", "tour"],
         "education": ["mba", "masters", "course", "tuition", "college", "degree"],
         "wedding": ["wedding", "marriage"]}
CATEGORIES = ["Dining", "Shopping", "Travel", "Groceries", "Entertainment", "Fuel", "Utilities", "Health", "Subscriptions", "Education"]
CAT_WORDS = {"food": "Dining", "eating out": "Dining", "restaurant": "Dining", "swiggy": "Dining", "zomato": "Dining",
             "grocery": "Groceries", "clothes": "Shopping", "amazon": "Shopping", "movies": "Entertainment", "petrol": "Fuel",
             "bills": "Utilities", "medical": "Health"}


def _has(t: str, *words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", t) for w in words)


def route(question: str) -> list[tuple[str, dict]]:
    """Returns a list of (tool_name, args). Empty list = not recognised."""
    t = question.lower()
    amounts = parse_amounts(question)
    calls: list[tuple[str, dict]] = []

    # --- purchase / affordability
    buy = _has(t, "afford", "buy", "purchase", "should i get", "can i get", "thinking of getting", "planning to buy", "take a loan for")
    item = next((k for k, ws in ITEMS.items() if _has(t, *ws)), None)
    if (buy or (item and amounts and _has(t, "loan", "emi", "worth"))) and amounts:
        args = {"price": max(amounts), "item_type": item or "other"}
        if len(amounts) > 1 and _has(t, "down", "downpayment", "upfront", "advance"):
            args["down_payment"] = sorted(amounts)[0] if len(amounts) == 2 else sorted(amounts)[-2]
        if (r := parse_rate(question)) is not None:
            args["interest_rate"] = r
        if (n := parse_tenure_months(question)) is not None:
            args["tenure_months"] = n
        if item:
            args["item_name"] = next((w for w in ITEMS[item] if w in t), item).title()
        return [("affordability", args)]
    if buy and item and not amounts:
        return [("__ask__", {"question": f"What is the approximate price of the {item} (and the down payment, if you have one in mind)?"})]

    # --- EMI
    if _has(t, "emi") and amounts and _has(t, "calculate", "what is", "what's", "what will", "how much", "emi for", "emi on"):
        return [("emi_calculator", {"principal": max(amounts), **({"interest_rate": r} if (r := parse_rate(question)) is not None else {}),
                                    **({"tenure_months": n} if (n := parse_tenure_months(question)) is not None else {})})]

    # --- FIRE / retirement
    if _has(t, "fire", "retire", "retirement", "financial independence", "financially independent", "financial freedom", "corpus", "stop working"):
        args = {}
        if (a := parse_age(question)) is not None:
            args["retirement_age"] = a
        if amounts and _has(t, "invest", "sip", "save", "put"):
            args["monthly_investment"] = amounts[0]
        calls.append(("fire_forecast", args))
    # --- runway
    if _has(t, "runway", "lose my job", "lost my job", "job loss", "laid off", "income stop", "stopped earning", "survive", "emergency fund", "how long will my savings", "how long would my savings"):
        calls.append(("runway", {}))
    # --- tax
    if _has(t, "tax", "regime", "80c", "itr"):
        calls.append(("tax_comparison", {"gross_income": max(amounts)} if amounts else {}))
    # --- debt
    if _has(t, "debt", "loan", "payoff", "pay off", "repay", "prepay", "avalanche", "snowball", "emis"):
        calls.append(("debts_and_payoff", {"extra_monthly": amounts[0]} if amounts and _has(t, "extra", "more", "additional", "prepay") else {}))
    # --- cards
    if _has(t, "credit card", "card", "utilisation", "utilization", "credit score", "cibil", "minimum due", "default"):
        calls.append(("credit_cards", {}))
    # --- investments
    if _has(t, "invest", "portfolio", "stock", "mutual fund", "sip", "equity", "diversif", "allocation", "returns"):
        if not any(c[0] == "fire_forecast" for c in calls) or _has(t, "portfolio", "stock", "mutual fund", "diversif", "allocation"):
            calls.append(("investments", {}))
    # --- net worth
    if _has(t, "net worth", "networth", "assets", "how rich", "worth"):
        calls.append(("net_worth", {}))
    # --- forecast
    if _has(t, "next month", "forecast", "predict", "upcoming"):
        calls.append(("spending_forecast", {}))
    # --- anomalies
    if _has(t, "unusual", "suspicious", "fraud", "anomal", "weird transaction", "strange"):
        calls.append(("unusual_transactions", {}))
    # --- spending
    cat = next((c for c in CATEGORIES if c.lower() in t), None) or next((v for k, v in CAT_WORDS.items() if k in t), None)
    if cat or (not any(c[0] == "spending_forecast" for c in calls) and _has(t, "spend", "spending", "expenses", "where does my money", "where is my money", "budget", "cut down", "overspend")):
        calls.append(("spending_by_category", {"category": cat} if cat else {}))
    if _has(t, "cash flow", "cashflow", "income", "saving rate", "savings rate", "how much do i save", "save each month", "saving enough"):
        calls.append(("cash_flow", {}))
    # --- insurance / goals / peers
    if _has(t, "insurance", "insured", "insur", "term plan", "health cover", "life cover"):
        calls.append(("insurance", {}))
    if _has(t, "goal"):
        calls.append(("goals", {}))
    if _has(t, "compare", "peers", "others", "people like me", "average person"):
        calls.append(("peer_comparison", {}))
    # --- broad questions
    if not calls and _has(t, "how am i doing", "financial health", "overview", "summary", "summarise", "summarize", "my finances",
                          "financially healthy", "health score", "am i doing"):
        calls = [("profile_summary", {}), ("recommendations", {})]
    if not calls and _has(t, "what should i do", "advice", "recommend", "improve", "priorit", "fix", "focus on", "next step"):
        calls = [("recommendations", {})]
    return calls[:3]

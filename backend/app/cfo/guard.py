"""Number-verification guard.

After the language model writes an answer, every number in it is checked against the
numbers the backend tools actually returned. If the model states a figure that is not
supported by the tool output, the answer is rejected and the rule-based text is used.
This is what stops the assistant from inventing financial figures.
"""
from __future__ import annotations

import re

_NUM = re.compile(r"(?<![A-Za-z])(₹|rs\.?\s*)?(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|l|k|%|x|×)?(?![A-Za-z\d])", re.I)
_MULT = {"cr": 1e7, "crore": 1e7, "crores": 1e7, "l": 1e5, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "k": 1e3}


def collect_numbers(obj, out: set | None = None) -> set:
    out = set() if out is None else out
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            try:
                out.add(float(m.group(2).replace(",", "")) * _MULT.get((m.group(3) or "").lower(), 1))
            except ValueError:
                pass
    return out


def _supported(value: float, facts: set, tol: float, abs_tol: float = 0.0) -> bool:
    """A figure is supported if it equals a fact (to rounding), or a monthly/annual conversion or complement of a fact
    almost exactly (0.1%): derived values get no slack, so coincidences with unrelated facts are not accepted."""
    if value == 0:
        return True
    for f in facts:
        if f and abs(value - f) <= max(tol * max(abs(f), 1e-9), abs_tol):
            return True
        for cand in (f * 12, f / 12, 100 - f if f <= 100 else None):
            if cand and abs(value - cand) <= min(tol, 0.001) * max(abs(cand), 1e-9):
                return True
    return False


# Published guideline values the assistant may quote (they are rules of thumb, not the user's data)
BENCHMARKS = {80.0, 30.0, 6.0, 3.0, 10.0, 20.0, 40.0, 50.0, 3.3, 4.0, 25.0, 12.0, 15.0, 100.0, 60.0, 75.0}


def verify(answer: str, facts: dict, question: str = "") -> dict:
    """Returns {"ok": bool, "unsupported": [...], "checked": int}."""
    allowed = collect_numbers(facts) | collect_numbers(question)
    unsupported, checked = [], 0
    for m in _NUM.finditer(answer):
        raw, unit = m.group(2).replace(",", ""), (m.group(3) or "").lower()
        try:
            v = float(raw)
        except ValueError:
            continue
        money = bool(m.group(1)) or unit in _MULT
        if not money and v in BENCHMARKS:
            continue
        if not money and unit not in {"%", "x", "×"} and v <= 31 and float(v).is_integer():
            continue  # small counts: list numbering, days, months
        if not money and 1900 <= v <= 2100 and float(v).is_integer():
            continue  # years
        checked += 1
        scaled = v * _MULT.get(unit, 1)
        # rounded figures like "₹1.2 L" are compared with a looser tolerance
        # exact rupee figures must match to rounding (0.5%); a lakh/crore figure is rounded by design (6%); other numbers 3%
        tol = 0.06 if unit in _MULT else 0.005 if money else 0.03
        if not (_supported(scaled, allowed, tol, 1.0 if money and unit not in _MULT else 0.0) or (unit == "%" and _supported(round(v), {round(a) for a in allowed if a <= 1000}, 0.0))):
            unsupported.append(m.group(0).strip())
    return {"ok": not unsupported, "unsupported": unsupported[:8], "checked": checked}

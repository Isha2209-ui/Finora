"""Incomplete profiles: every endpoint works, nothing crashes, and missing data is reported as missing - never as 0.

Each profile is built with ONLY what a person might have typed in (see partial_profiles.py) and owned by a test account.
"""
import io
import re
import zipfile

import pytest
from sqlalchemy import select

from app import models as M
from app.database import SessionLocal

from .conftest import signed_in_client
from .partial_profiles import BUILDERS

GETS = ["", "/analysis", "/accounts", "/transactions", "/recommendations", "/briefing?use_llm=false", "/report.pdf",
        "/export.zip", "/transactions.csv", "/data-summary", "/records", "/chat"]
POSTS = [("/fire", {}), ("/fire", {"annual_expenses": 480000}), ("/decision", {"price": 500000, "down_payment": 100000}),
         ("/payoff", {"extra_monthly": 5000}), ("/analyze", None)]
# one question per AI CFO tool
QUESTIONS = ["How am I doing overall?", "What is my savings rate?", "Where can I cut my spending?", "How much do I spend on dining?",
             "What is my net worth?", "How is my portfolio doing?", "How is my credit card usage?", "How should I pay off my loans?",
             "How long would my savings last if I lose my job?", "When can I retire?", "Can I afford a 6 lakh car?",
             "What is the EMI for 5 lakh at 10% for 60 months?", "Which tax regime is better for me?", "What will I spend next month?",
             "Any unusual transactions?", "Am I insured enough?", "How are my goals going?", "How do I compare with people like me?",
             "What should I do first?"]
BAD_TEXT = re.compile(r"\bNone\b|\bnan\b|None%|: \.|₹None", re.I)


@pytest.fixture(scope="module")
def gina():
    c = signed_in_client("gina")
    c.me = c.get("/api/auth/me").json()["account"]["id"]
    return c


def _make(owner_id: int, name: str) -> str:
    with SessionLocal() as db:
        u = M.User(internal_id=f"FP_PARTIAL_{name.upper()[:14]}_{owner_id}", name="Partial Person", age=31, occupation="Engineer",
                   employment_type="salaried", city="Pune", kind="private", archetype="custom", owner_id=owner_id)
        db.add(u)
        db.flush()
        BUILDERS[name](db, u.id)
        db.commit()
        return u.internal_id


@pytest.mark.parametrize("name", list(BUILDERS))
def test_every_endpoint_works_on_partial_profile(gina, name):
    pid = _make(gina.me, name)
    for path in GETS:
        r = gina.get(f"/api/profiles/{pid}{path}")
        assert r.status_code == 200, (name, path, r.text[:300])
        if r.headers["content-type"].startswith("application/json"):
            assert "None%" not in r.text and "NaN" not in r.text, (name, path)
    for path, body in POSTS:
        r = gina.post(f"/api/profiles/{pid}{path}", json=body) if body is not None else gina.post(f"/api/profiles/{pid}{path}")
        assert r.status_code == 200, (name, path, r.text[:300])
    problems = []
    for q in QUESTIONS:
        r = gina.post(f"/api/profiles/{pid}/chat", json={"message": q, "use_llm": False})
        if r.status_code != 200 or not r.json().get("answer") or BAD_TEXT.search(r.json()["answer"]):
            problems.append((q, r.status_code, r.text[:260]))
    assert not problems, (name, problems)
    z = zipfile.ZipFile(io.BytesIO(gina.get(f"/api/profiles/{pid}/export.zip").content))
    assert "net_worth.csv" in z.namelist()


@pytest.mark.parametrize("name", list(BUILDERS))
def test_missing_data_is_never_counted_as_zero(gina, name):
    pid = f"FP_PARTIAL_{name.upper()[:14]}_{gina.me}"
    with SessionLocal() as db:
        if not db.scalar(select(M.User.id).where(M.User.internal_id == pid)):
            pid = _make(gina.me, name)
    a = gina.get(f"/api/profiles/{pid}/analysis").json()
    cf, hs = a["cash_flow"], a["health_score"]
    if not cf["spending_known"]:
        assert cf["avg_monthly_expenses"] is None and cf["avg_savings_rate_pct"] is None
        assert a["liquidity"]["runway_months"] is None and a["fire"]["available"] is False
        assert "Emergency fund" in hs["not_assessed"] and "EMERGENCY_FUND" not in {r["code"] for r in a["recommendations"]}
        assert a["ml"]["forecast"]["available"] is False
    if not cf["income_known"]:
        assert cf["avg_monthly_income"] is None and "Investing" in hs["not_assessed"]
        assert a["tax"]["available"] is False
        assert "LOW_SAVINGS" not in {r["code"] for r in a["recommendations"]}
    if not (cf["income_known"] or cf["spending_known"]):
        assert hs["score"] is None and hs["band"] == "Not enough data"       # an empty profile is not "healthy"
    if hs["score"] is not None:
        assert set(hs["pillars"]) & {"Savings", "Emergency fund", "Investing"}
    assert 0 <= a["completeness"]["score_pct"] <= 100
    present = {i["item"] for i in a["completeness"]["items"] if i["present"]}
    assert ("Bank accounts" in present) == bool(gina.get(f"/api/profiles/{pid}/records").json()["bank_accounts"])


def test_full_manual_profile_gets_a_complete_analysis(gina):
    pid = f"FP_PARTIAL_FULL_MANUAL_{gina.me}"
    with SessionLocal() as db:
        if not db.scalar(select(M.User.id).where(M.User.internal_id == pid)):
            pid = _make(gina.me, "full_manual")
    a = gina.get(f"/api/profiles/{pid}/analysis").json()
    assert a["ml_errors"] == {} and a["fire"]["available"] and a["health_score"]["score"] is not None
    assert not a["health_score"]["not_assessed"] and a["tax"]["available"]
    b = a["net_worth"]["breakdown"]
    assert {"Bank balances", "Fixed deposits", "Equity", "Mutual funds", "Gold", "Retirement (EPF/PPF/NPS)", "Real estate", "Other",
            "Cash in hand"} <= set(b)
    assert a["completeness"]["score_pct"] == 100

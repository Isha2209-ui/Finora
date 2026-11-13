"""AI CFO: routing, tool use, number verification and safe fallbacks (runs without a language model)."""
import pytest

from app.cfo import guard, router

QUESTIONS = [
    ("Can I afford a 12 lakh car?", "affordability"), ("Should I buy an iPhone for 1.3L with 20k down at 15% for 12 months?", "affordability"),
    ("When can I retire?", "fire_forecast"), ("What if I invest 40000 a month and retire at 55?", "fire_forecast"),
    ("How long would my savings last if I lose my job?", "runway"), ("Which tax regime is better for me?", "tax_comparison"),
    ("How should I pay off my loans?", "debts_and_payoff"), ("How are my credit cards doing?", "credit_cards"),
    ("How much do I spend on dining?", "spending_by_category"), ("What is my net worth?", "net_worth"),
    ("What will I spend next month?", "spending_forecast"), ("Any unusual transactions?", "unusual_transactions"),
    ("How am I doing financially?", "profile_summary"), ("What should I do first?", "recommendations"),
    ("emi for 5 lakh at 11% for 3 years", "emi_calculator"), ("How is my portfolio?", "investments"),
    ("Am I insured enough?", "insurance"), ("How are my goals going?", "goals"),
    ("How do I compare with others?", "peer_comparison"), ("Is my emergency fund enough?", "runway"),
]


@pytest.mark.parametrize("q,tool", QUESTIONS)
@pytest.mark.parametrize("uid", ["FINORA_USER_001", "FINORA_USER_002", "FINORA_USER_003", "FINORA_USER_004"])
def test_cfo_answers_use_the_right_tool_and_only_real_numbers(client, uid, q, tool):
    r = client.post(f"/api/profiles/{uid}/chat", json={"message": q, "use_llm": False}).json()
    assert tool in r["tools_used"], r
    assert "licensed financial advisor" in r["answer"]
    check = guard.verify(r["answer"], r["facts"], q)
    assert check["ok"], check                                # every number in the answer exists in the tool output


def test_amount_parsing():
    assert router.parse_amounts("a 12 lakh car") == [1_200_000]
    assert router.parse_amounts("₹8,00,000 with 1.5L down") == [800_000, 150_000]
    assert router.parse_amounts("1.2 cr flat, 50k booking") == [12_000_000, 50_000]
    assert router.parse_amounts("at 9% for 5 years") == []
    assert router.parse_rate("at 9.5% for 5 years") == 9.5 and router.parse_tenure_months("for 5 years") == 60


def test_affordability_arguments_are_extracted(client):
    r = client.post("/api/profiles/FINORA_USER_001/chat", json={"message": "Can I buy a 9 lakh car with 3 lakh down at 9% for 4 years?", "use_llm": False}).json()
    f = r["facts"]["affordability"]
    assert (f["price"], f["down_payment"], f["interest_rate_pct"], f["tenure_months"]) == (900000, 300000, 9.0, 48)
    assert f["emi"] == 14931                                  # EMI on 6,00,000 at 9% for 48 months


def test_guard_rejects_invented_numbers():
    facts = {"emi": 20162, "net_worth": 13_461_173, "rate": 9.5}
    assert guard.verify("Your EMI is ₹20,162 at 9.5% and net worth is ₹1.35 Cr.", facts)["ok"]
    bad = guard.verify("Your EMI is ₹18,500 and your net worth is ₹2 Cr.", facts)
    assert not bad["ok"] and len(bad["unsupported"]) == 2


def test_out_of_scope_and_missing_details(client):
    r = client.post("/api/profiles/FINORA_USER_001/chat", json={"message": "Who won the cricket match?", "use_llm": False}).json()
    assert r["tools_used"] == [] and "finance assistant" in r["answer"]
    r = client.post("/api/profiles/FINORA_USER_001/chat", json={"message": "I want to buy a car", "use_llm": False}).json()
    assert "price" in r["answer"].lower()
    r = client.post("/api/profiles/FINORA_USER_001/chat", json={"message": "What is a SIP?", "use_llm": False}).json()
    assert "Systematic Investment Plan" in r["answer"]


def test_briefing_and_history(client):
    b = client.get("/api/profiles/FINORA_USER_002/briefing", params={"use_llm": False}).json()
    assert b["briefing"] and b["priorities"] and guard.verify(b["briefing"], b["facts"])["ok"]
    assert len(client.get("/api/profiles/FINORA_USER_001/chat").json()) >= 2
    assert client.delete("/api/profiles/FINORA_USER_001/chat").json()["cleared"]
    assert "available" in client.get("/api/cfo/status").json()

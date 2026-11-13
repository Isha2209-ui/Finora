"""API tests: every endpoint, all four demo PANs, plus invalid input."""
import io

import pytest

from .conftest import DEMO


@pytest.mark.parametrize("pan,uid", list(DEMO.items()))
def test_lookup_ok(client, pan, uid):
    r = client.post("/api/lookup", json={"pan": pan.lower()})
    assert r.status_code == 200 and r.json()["profile"]["internal_id"] == uid
    assert r.json()["profile"]["pan_masked"] == pan[:5] + "****" + pan[-1]
    assert pan not in r.text                                            # the full PAN is never echoed back


@pytest.mark.parametrize("pan,code", [("", 422), ("ABC", 422), ("12345ABCDE", 422), ("ABCDE12345", 422), ("ZZZZZ9999Z", 404)])
def test_lookup_invalid(client, pan, code):
    assert client.post("/api/lookup", json={"pan": pan}).status_code == code


def test_health_and_profiles(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and all(h["models"].values()) and h["users"] >= 244
    assert len(client.get("/api/profiles").json()) >= 4
    assert client.get("/api/profiles/NOPE").status_code == 404


@pytest.mark.parametrize("uid", list(DEMO.values()))
def test_analysis_complete_and_consistent(analyses, uid):
    a = analyses[uid]
    for key in ["profile", "cash_flow", "net_worth", "allocation", "liquidity", "credit", "debt", "insurance", "investments",
                "budget", "fire", "tax", "health_score", "ml", "recommendations", "alerts"]:
        assert key in a, key
    assert a["ml_errors"] == {}
    nw = a["net_worth"]
    assert nw["net_worth"] == pytest.approx(nw["total_assets"] - nw["total_liabilities"], abs=1)
    assert sum(nw["breakdown"].values()) == pytest.approx(nw["total_assets"], abs=2)
    cf = a["cash_flow"]
    assert cf["avg_monthly_savings"] == pytest.approx(cf["avg_monthly_income"] - cf["avg_monthly_expenses"], abs=1)
    for m in cf["monthly_series"]:
        assert m["savings"] == pytest.approx(m["income"] - m["expenses"], abs=0.02)
    assert sum(a["allocation"]["allocation_pct"].values()) == pytest.approx(100, abs=0.1)
    assert 0 <= a["health_score"]["score"] <= 100
    for r in a["recommendations"]:
        assert r["finding"] and r["evidence"] and r["action"] and r["priority"] in {"high", "medium", "low"}


def test_profiles_show_their_designed_situations(analyses):
    a1, a2, a3, a4 = (analyses[f"FINORA_USER_00{i}"] for i in range(1, 5))
    assert a1["health_score"]["score"] > 80 and a1["cash_flow"]["avg_savings_rate_pct"] > 30
    assert a2["cash_flow"]["avg_savings_rate_pct"] < 0 and a2["credit"]["overall_utilisation_pct"] > 60
    assert a2["ml"]["credit_risk"]["overall_risk_band"] in {"high", "very high"}
    assert a1["ml"]["credit_risk"]["overall_risk_band"] == "low"
    assert a3["debt"]["risk_band"] in {"high", "very high"} and a3["net_worth"]["breakdown"]["Real estate"] > 1e7
    assert a4["cash_flow"]["income_volatility_pct"] > 20 and not a4["insurance"]["has_health"]
    codes = lambda a: {r["code"] for r in a["recommendations"]}  # noqa: E731
    assert "DEFICIT" in codes(a2) and "HIGH_EMI" in codes(a3) and "HEALTH_COVER" in codes(a4)


def test_planted_anomalies_are_caught(client):
    for uid in DEMO.values():
        t = client.get(f"/api/profiles/{uid}/transactions", params={"flagged_only": True, "limit": 200}).json()
        assert t["anomaly_summary"]["flagged_count"] >= 1
        assert all(i["flagged"] and i["reasons"] for i in t["items"])


def test_transactions_filters(client):
    uid = "FINORA_USER_001"
    all_ = client.get(f"/api/profiles/{uid}/transactions", params={"limit": 5}).json()
    assert all_["total"] > 300 and len(all_["items"]) == 5
    d = client.get(f"/api/profiles/{uid}/transactions", params={"category": "Dining", "limit": 500}).json()
    assert d["total"] > 0 and {i["category"] for i in d["items"]} == {"Dining"}
    m = client.get(f"/api/profiles/{uid}/transactions", params={"month": "2026-10", "limit": 500}).json()
    assert all(i["date"].startswith("2026-10") for i in m["items"])
    s = client.get(f"/api/profiles/{uid}/transactions", params={"search": "swiggy", "limit": 50}).json()
    assert s["total"] > 0


def test_accounts_and_cards(client):
    a = client.get("/api/profiles/FINORA_USER_002/accounts").json()
    assert len(a["accounts"]) == 2 and len(a["cards"]) == 3 and a["credit_risk"]["has_cards"]


def test_fire_what_if(client):
    base = client.post("/api/profiles/FINORA_USER_001/fire", json={}).json()
    more = client.post("/api/profiles/FINORA_USER_001/fire", json={"monthly_investment": 80000}).json()
    assert more["fire_age"] < base["fire_age"] and more["success_probability_pct"] >= base["success_probability_pct"]
    assert base["corpus_by_age"] and base["runway"]["runway_months"] > 0
    assert client.post("/api/profiles/FINORA_USER_001/fire", json={"retirement_age": 10}).status_code == 422


def test_decision_simulator(client):
    body = {"item_type": "car", "item_name": "Hatchback", "price": 700000, "down_payment": 200000, "interest_rate": 9.5, "tenure_months": 60}
    ok = client.post("/api/profiles/FINORA_USER_001/decision", json=body).json()
    bad = client.post("/api/profiles/FINORA_USER_002/decision", json=body).json()
    assert ok["plan"]["verdict"] == "AFFORDABLE" and bad["plan"]["verdict"] == "NOT ADVISABLE"
    assert ok["plan"]["emi"] == 10501                                    # EMI on 5,00,000 at 9.5% for 60 months
    assert ok["plan"]["impact"]["runway_months"]["after"] < ok["plan"]["impact"]["runway_months"]["before"]
    assert bad["plan"]["reasons"] and ok["alternatives"]
    assert client.post("/api/profiles/FINORA_USER_001/decision", json={"price": -5}).status_code == 422


def test_tax_and_payoff(client):
    t = client.post("/api/tax/compare", json={"gross_income": 1575000}).json()
    assert t["new"]["total_tax"] == 109200 and t["better_regime"] == "new"
    p0 = client.post("/api/profiles/FINORA_USER_003/payoff", json={"extra_monthly": 0}).json()
    p1 = client.post("/api/profiles/FINORA_USER_003/payoff", json={"extra_monthly": 20000}).json()
    assert p1["avalanche"]["months_to_debt_free"] < p0["avalanche"]["months_to_debt_free"]
    assert p1["vs_no_extra"]["interest_saved"] > 0
    assert client.post("/api/profiles/FINORA_USER_001/payoff", json={"extra_monthly": 0}).json()["has_debt"] in (True, False)


def test_reports(client):
    r = client.get("/api/profiles/FINORA_USER_003/report.pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-" and len(r.content) > 20000
    z = client.get("/api/profiles/FINORA_USER_003/export.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"
    c = client.get("/api/profiles/FINORA_USER_003/transactions.csv")
    assert c.status_code == 200 and c.text.startswith("date,amount")
    assert len(client.get("/api/profiles/FINORA_USER_003/reports").json()) >= 1


def test_model_lab_and_categorise(client):
    m = client.get("/api/models/metrics").json()
    assert {"credit_risk", "categoriser", "anomaly", "forecast", "peers"} <= set(m)
    c = client.post("/api/categorise", json={"texts": ["UPI/DR/1234567890/ZOMATO/HDFC/zomato@ybl", "ATM WDL SBI ATM DELHI"]}).json()
    assert [x["category"] for x in c] == ["Dining", "Cash"]


def test_full_lifecycle_create_upload_analyse_delete(client):
    pan = "TESTP1234Q"
    client.delete("/api/profiles/FINORA_USER_900")
    r = client.post("/api/profiles", json={"name": "Test User", "pan": pan, "age": 30, "monthly_income": 90000, "bank_balance": 150000})
    assert r.status_code == 200, r.text
    uid = r.json()["profile"]["internal_id"]
    try:
        assert client.post("/api/profiles", json={"name": "Dup", "pan": pan, "age": 30, "monthly_income": 1}).status_code == 409
        rows = ["Date,Narration,Withdrawal,Deposit"]
        for m in range(4, 11):
            rows += [f"05/{m:02d}/2026,IMPS/P2A/123456789012/RENT FLAT,20000,", f"08/{m:02d}/2026,UPI/DR/123456789012/SWIGGY/YESB/swiggy@ybl/Payment,{600 + m * 10},",
                     f"11/{m:02d}/2026,POS 4521XXXXXXXX1234 AMAZON BANGALORE,{2500 + m * 50},", f"14/{m:02d}/2026,UPI/DR/123456789012/BIGBASKET/ICIC/bigbasket@ybl/Payment,3200,",
                     f"19/{m:02d}/2026,BIL/BPAY/556677889/AIRTEL/AUTOPAY,799,", f"22/{m:02d}/2026,UPI/DR/123456789012/UBER/AXIS/uber@okaxis/Payment,{350 + m},"]
        rows.append("25/10/2026,POS 4521XXXXXXXX1234 MYNTRA MUMBAI,48000,")     # an obviously unusual purchase
        up = client.post(f"/api/profiles/{uid}/upload", files={"file": ("stmt.csv", io.BytesIO("\n".join(rows).encode()), "text/csv")})
        assert up.status_code == 200, up.text
        u = up.json()
        assert u["transactions_added"] == 43 and u["categorised_by_model"] == 43
        assert u["by_category"]["Rent"] == 7 and u["by_category"]["Dining"] == 7 and u["by_category"]["Shopping"] == 8
        again = client.post(f"/api/profiles/{uid}/upload", files={"file": ("stmt.csv", io.BytesIO("\n".join(rows).encode()), "text/csv")}).json()
        assert again["transactions_added"] == 0 and again["duplicates_skipped"] == 43      # re-upload is idempotent
        a = client.get(f"/api/profiles/{uid}/analysis").json()
        assert a["ml_errors"] == {} and a["cash_flow"]["avg_monthly_expenses"] > 20000
        flagged = [f for f in a["ml"]["anomaly"]["flagged"] if f["amount"] == 48000]
        assert flagged and flagged[0]["severity"] == "high"                                  # the model catches it on brand-new data
        assert a["ml"]["forecast"]["available"]
        tx = client.get(f"/api/profiles/{uid}/transactions", params={"limit": 1}).json()["items"][0]
        p = client.patch(f"/api/profiles/{uid}/transactions/{tx['id']}", json={"category": "food"}).json()
        assert p["category"] == "Dining" and p["category_source"] == "user"
        add = client.post(f"/api/profiles/{uid}/transactions", json={"date": "2026-10-28", "amount": 420, "description": "UPI/DR/999/ZOMATO/HDFC/zomato@ybl"}).json()
        assert add["category"] == "Dining" and add["category_source"] == "model"
        assert client.delete(f"/api/profiles/{uid}/transactions/{add['id']}").status_code == 200
        assert client.patch(f"/api/profiles/{uid}", json={"retirement_age_target": 52}).json()["retirement_age_target"] == 52
        bad = client.post(f"/api/profiles/{uid}/upload", files={"file": ("x.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")})
        assert bad.status_code == 422
    finally:
        assert client.delete(f"/api/profiles/{uid}").status_code == 200
    assert client.post("/api/lookup", json={"pan": pan}).status_code == 404
    assert client.delete("/api/profiles/FINORA_USER_001").status_code == 403                # demo profiles are protected


def test_recommendation_status(client):
    recs = client.get("/api/profiles/FINORA_USER_004/recommendations").json()
    assert recs
    rid = recs[0]["id"]
    assert client.patch(f"/api/profiles/FINORA_USER_004/recommendations/{rid}", json={"status": "accepted"}).json()["status"] == "accepted"
    client.patch(f"/api/profiles/FINORA_USER_004/recommendations/{rid}", json={"status": "open"})

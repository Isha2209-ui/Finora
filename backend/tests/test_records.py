"""Phase 3: manual entry of a whole financial identity.

Not just "the form saves": every test that adds or changes a record then checks that the change appears in the real
outputs - net worth, cash flow, ratios, health score, recommendations, FIRE, model results, report and export -
with exact arithmetic where the formula is simple enough to state.
"""
import io
import zipfile

import pytest
from sqlalchemy import select

from app import models as M
from app.database import SessionLocal

from app.ml import provenance as PV

from .conftest import signed_in_client


def latest_trained(name):
    """The newest TRAINED real-data artifact of a model (active or not), checksum-verified."""
    import json, joblib
    d = sorted((PV.REAL_DIR / name).glob("*/provenance.json"))[-1].parent
    prov = json.loads((d / "provenance.json").read_text())
    assert prov["data_status"] == "real" and PV.sha256(d / "model.joblib") == prov["artifact"]["sha256"]
    return joblib.load(d / "model.joblib")

VALID = {
    "bank_accounts": {"bank_name": "HDFC Bank", "account_type": "savings", "last4": "1234", "balance": 250000, "interest_rate": 3.0, "is_primary": True},
    "credit_cards": {"issuer": "ICICI Bank", "card_name": "Coral", "last4": "4321", "credit_limit": 100000, "outstanding": 20000, "min_due": 1000, "due_day": 12, "apr": 42},
    "loans": {"loan_type": "Personal Loan", "lender": "Bajaj Finance", "principal": 500000, "balance": 300000, "emi": 15000, "interest_rate": 14, "tenure_months": 36, "remaining_months": 22},
    "insurance": {"kind": "health", "insurer": "Niva Bupa", "cover": 500000, "annual_premium": 12000},
    "stocks": {"symbol": "INFY", "company": "Infosys", "sector": "IT", "quantity": 40, "avg_buy_price": 1400, "current_price": 1650, "buy_date": "2024-05-10"},
    "mutual_funds": {"scheme": "UTI Nifty 50 Index Fund", "fund_type": "index", "units": 100, "avg_nav": 120, "current_nav": 150, "start_date": "2023-01-05"},
    "sips": {"scheme": "UTI Nifty 50 Index Fund", "amount": 5000, "sip_day": 5, "start_date": "2023-01-05", "status": "active"},
    "deposits": {"kind": "FD", "bank": "SBI", "principal": 100000, "interest_rate": 7, "start_date": "2026-10-31", "maturity_date": "2027-10-31"},
    "other_assets": {"kind": "ppf", "value": 300000},
    "properties": {"kind": "Apartment", "city": "Pune", "purchase_value": 5000000, "purchase_date": "2021-03-01", "current_value": 6500000},
    "goals": {"name": "Car", "target_amount": 800000, "target_date": "2028-10-31", "current_amount": 200000},
    "income": {"amount": 100000, "source": "Salary", "date": "2026-10-01"},
    "recurring": {"name": "Netflix", "category": "Entertainment", "amount": 649, "frequency": "monthly", "day_of_month": 7},
    "transactions": {"date": "2026-10-05", "amount": 640, "description": "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment"},
}
PATCHES = {
    "bank_accounts": {"balance": 260000}, "credit_cards": {"outstanding": 30000}, "loans": {"balance": 290000, "remaining_months": 21},
    "insurance": {"cover": 1000000}, "stocks": {"current_price": 1700}, "mutual_funds": {"current_nav": 155}, "sips": {"status": "paused"},
    "deposits": {"interest_rate": 7.25}, "other_assets": {"value": 320000}, "properties": {"current_value": 6600000},
    "goals": {"current_amount": 250000}, "income": {"amount": 105000}, "recurring": {"amount": 799},
    "transactions": {"amount": 700},
}
INVALID = {
    "bank_accounts": {**VALID["bank_accounts"], "last4": "123456789012"},          # full account number refused
    "credit_cards": {**VALID["credit_cards"], "min_due": 50000},                     # min due > outstanding
    "loans": {**VALID["loans"], "remaining_months": 40},                             # remaining > tenure
    "insurance": {**VALID["insurance"], "kind": "car"},
    "stocks": {**VALID["stocks"], "buy_date": "2030-01-01"},                         # future
    "mutual_funds": {**VALID["mutual_funds"], "units": -5},
    "sips": {**VALID["sips"], "sip_day": 31},
    "deposits": {**VALID["deposits"], "maturity_date": "2025-01-01"},                # before start
    "other_assets": {**VALID["other_assets"], "kind": "lottery"},
    "properties": {**VALID["properties"], "monthly_rent": 20000},                    # rent on self-occupied
    "goals": {**VALID["goals"], "target_date": "2020-01-01"},                        # in the past
    "income": {**VALID["income"], "amount": 0},
    "recurring": {**VALID["recurring"], "category": "Yachts"},
    "transactions": {**VALID["transactions"], "category": "Yachts"},
}


def new_private(c, name="Manual Person", age=32, retire=55):
    r = c.post("/api/profiles", json={"name": name, "age": age, "retirement_age_target": retire, "city": "Pune"})
    assert r.status_code == 200, r.text
    return r.json()["profile"]["internal_id"]


def rec(c, pid, typ, body):
    r = c.post(f"/api/profiles/{pid}/records/{typ}", json=body)
    assert r.status_code == 201, (typ, r.text)
    return r.json()


def analysis(c, pid):
    r = c.get(f"/api/profiles/{pid}/analysis")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def erin():
    return signed_in_client("erin")


@pytest.fixture(scope="module")
def frank():
    return signed_in_client("frank")


# ---------------------------------------------------------------- creation is honest
def test_new_profile_contains_nothing_invented(erin):
    pid = new_private(erin)
    counts = erin.get(f"/api/profiles/{pid}/records").json()
    assert set(counts) == set(VALID) and sum(counts.values()) == 0          # no dummy accounts, income or transactions
    a = analysis(erin, pid)
    assert a["net_worth"]["net_worth"] == 0 and a["cash_flow"]["available"] is False
    assert a["health_score"]["score"] is None and a["fire"]["available"] is False
    assert a["completeness"]["score_pct"] < 20 and "Income" in a["completeness"]["missing"]
    assert erin.post("/api/profiles", json={"name": "X Y", "age": 30, "monthly_income": 90000}).status_code == 422   # field no longer exists


def test_schema_describes_every_record_type(erin):
    s = {t["type"]: t for t in erin.get("/api/records/schema").json()}
    assert set(s) == set(VALID)
    f = {x["name"]: x for x in s["other_assets"]["fields"]}
    assert f["kind"]["type"] == "select" and "epf" in f["kind"]["options"] and f["value"]["rules"]["ge"] == 0
    assert {x["name"]: x for x in s["loans"]["fields"]}["property_id"]["ref"] == "property_id"


# ---------------------------------------------------------------- CRUD + validation for every type
@pytest.mark.parametrize("typ", list(VALID))
def test_crud_and_validation(erin, typ):
    pid = new_private(erin, f"Crud {typ}")
    bad = erin.post(f"/api/profiles/{pid}/records/{typ}", json=INVALID[typ])
    assert bad.status_code == 422 and bad.json()["detail"]
    assert erin.post(f"/api/profiles/{pid}/records/{typ}", json={**VALID[typ], "hacker_field": 1}).status_code == 422
    made = rec(erin, pid, typ, VALID[typ])
    items = erin.get(f"/api/profiles/{pid}/records/{typ}").json()["items"]
    assert [i["id"] for i in items] == [made["id"]] and made["_title"]
    p = erin.patch(f"/api/profiles/{pid}/records/{typ}/{made['id']}", json=PATCHES[typ])
    assert p.status_code == 200, p.text
    for k, v in PATCHES[typ].items():
        assert p.json()[k] == v
    # a PATCH is validated on the merged record (cross-field rules still apply)
    worse = {"loans": {"remaining_months": 99}, "deposits": {"maturity_date": "2020-01-01"}, "credit_cards": {"min_due": 999999}}
    if typ in worse:
        assert erin.patch(f"/api/profiles/{pid}/records/{typ}/{made['id']}", json=worse[typ]).status_code == 422
    assert erin.patch(f"/api/profiles/{pid}/records/{typ}/{made['id']}", json={"nope": 1}).status_code == 422
    assert erin.delete(f"/api/profiles/{pid}/records/{typ}/{made['id']}").status_code == 200
    assert erin.get(f"/api/profiles/{pid}/records/{typ}").json()["total"] == 0
    assert erin.delete(f"/api/profiles/{pid}/records/{typ}/{made['id']}").status_code == 404


def test_full_account_numbers_are_never_stored(erin):
    pid = new_private(erin, "Masking")
    a = rec(erin, pid, "bank_accounts", VALID["bank_accounts"])
    with SessionLocal() as db:
        assert db.get(M.BankAccount, a["id"]).account_masked == "XXXX1234"
    assert a["last4"] == "1234" and "account_masked" not in a


# ---------------------------------------------------------------- ownership, templates, references
def test_other_accounts_and_templates_cannot_touch_records(erin, frank):
    pid = new_private(erin, "Owned")
    st = rec(erin, pid, "stocks", VALID["stocks"])
    assert frank.get(f"/api/profiles/{pid}/records/stocks").status_code == 404
    assert frank.post(f"/api/profiles/{pid}/records/stocks", json=VALID["stocks"]).status_code == 404
    assert frank.patch(f"/api/profiles/{pid}/records/stocks/{st['id']}", json={"quantity": 1}).status_code == 404
    assert frank.delete(f"/api/profiles/{pid}/records/stocks/{st['id']}").status_code == 404
    fp = new_private(frank, "Frank Own")                               # frank's own profile cannot address erin's record
    assert frank.patch(f"/api/profiles/{fp}/records/stocks/{st['id']}", json={"quantity": 1}).status_code == 404
    assert frank.delete(f"/api/profiles/{fp}/records/stocks/{st['id']}").status_code == 404
    tpl = "FINORA_USER_001"
    assert frank.get(f"/api/profiles/{tpl}/records/stocks").json()["read_only"] is True
    tst = frank.get(f"/api/profiles/{tpl}/records/stocks").json()["items"][0]
    assert frank.post(f"/api/profiles/{tpl}/records/stocks", json=VALID["stocks"]).status_code == 403
    assert frank.patch(f"/api/profiles/{tpl}/records/stocks/{tst['id']}", json={"quantity": 1}).status_code == 403
    assert frank.delete(f"/api/profiles/{tpl}/records/stocks/{tst['id']}").status_code == 403
    assert frank.post(f"/api/profiles/{pid}/records/nonsense", json={}).status_code == 404


def test_references_must_belong_to_the_same_profile(erin, frank):
    pid = new_private(erin, "Refs")
    fp = new_private(frank, "Frank Refs")
    frank_prop = rec(frank, fp, "properties", VALID["properties"])
    frank_acct = rec(frank, fp, "bank_accounts", VALID["bank_accounts"])
    assert erin.post(f"/api/profiles/{pid}/records/loans", json={**VALID["loans"], "property_id": frank_prop["id"]}).status_code == 422
    assert erin.post(f"/api/profiles/{pid}/records/transactions", json={**VALID["transactions"], "account_id": frank_acct["id"]}).status_code == 422
    assert erin.post(f"/api/profiles/{pid}/records/income", json={**VALID["income"], "account_id": frank_acct["id"]}).status_code == 422
    own = rec(erin, pid, "bank_accounts", VALID["bank_accounts"])
    assert rec(erin, pid, "income", {**VALID["income"], "account_id": own["id"]})["account_id"] == own["id"]


def test_delete_with_dependents_needs_cascade_and_never_drops_loans(erin):
    pid = new_private(erin, "Cascade")
    acct = rec(erin, pid, "bank_accounts", VALID["bank_accounts"])
    rec(erin, pid, "transactions", {**VALID["transactions"], "account_id": acct["id"]})
    rec(erin, pid, "income", {**VALID["income"], "account_id": acct["id"]})
    r = erin.delete(f"/api/profiles/{pid}/records/bank_accounts/{acct['id']}")
    assert r.status_code == 409 and "1 transactions" in r.json()["detail"]
    r = erin.delete(f"/api/profiles/{pid}/records/bank_accounts/{acct['id']}", params={"cascade": True})
    assert r.status_code == 200 and r.json()["also_removed"] == {"transactions": 1, "income records": 1}
    prop = rec(erin, pid, "properties", VALID["properties"])
    loan = rec(erin, pid, "loans", {**VALID["loans"], "loan_type": "Home Loan", "property_id": prop["id"]})
    erin.delete(f"/api/profiles/{pid}/records/properties/{prop['id']}", params={"cascade": True})
    loans = erin.get(f"/api/profiles/{pid}/records/loans").json()["items"]
    assert [x["id"] for x in loans] == [loan["id"]] and loans[0]["property_id"] is None


def test_transactions_are_categorised_by_the_model_unless_given(erin):
    pid = new_private(erin, "Cats")
    from app.ml import categoriser
    t = rec(erin, pid, "transactions", VALID["transactions"])
    # merchant text: decided by the approved categoriser, with its confidence stored and low confidence sent for review
    # (which category it picks for an Indian narration is not asserted: Indian accuracy is not established)
    want = categoriser.safe_predict([VALID["transactions"]["description"]])[0]
    assert t["category_source"] == want["source"] and t["category"] == want["category"]
    if want["source"] == "model":
        assert t["confidence"] == want["confidence"] and t["needs_review"] == (True if categoriser.SUGGESTION_ONLY else want["confidence"] < 0.5)
    t2 = rec(erin, pid, "transactions", {**VALID["transactions"], "category": "Groceries"})
    assert t2["category"] == "Groceries" and t2["category_source"] == "user"
    p = erin.patch(f"/api/profiles/{pid}/records/transactions/{t['id']}", json={"description": "ATM WDL SBI ATM DELHI"}).json()
    assert p["category"] == "Cash" and p["category_source"] == "rule"      # a suggested category follows the new text (Cash: rule)
    p = erin.patch(f"/api/profiles/{pid}/records/transactions/{t2['id']}", json={"description": "ATM WDL SBI ATM DELHI"}).json()
    assert p["category"] == "Groceries"                                    # a category the user chose is kept


def test_writes_are_audited_without_values(erin):
    pid = new_private(erin, "Audit")
    acct = rec(erin, pid, "bank_accounts", {**VALID["bank_accounts"], "balance": 987654})
    erin.patch(f"/api/profiles/{pid}/records/bank_accounts/{acct['id']}", json={"balance": 876543})
    erin.delete(f"/api/profiles/{pid}/records/bank_accounts/{acct['id']}")
    acts = [a for a in erin.get("/api/auth/activity").json() if a["action"].startswith("record.")][:3]
    assert [a["action"] for a in acts] == ["record.delete", "record.update", "record.create"]
    assert acts[1]["detail"] == {"type": "bank_accounts", "id": acct["id"], "fields": ["balance"]}
    assert "987654" not in str(acts) and "876543" not in str(acts)


# ---------------------------------------------------------------- the important part: changes reach the numbers
def test_every_entry_flows_into_the_analysis(erin):
    pid = new_private(erin, "Propagation", age=32, retire=55)

    acct = rec(erin, pid, "bank_accounts", {**VALID["bank_accounts"], "balance": 300000})
    a = analysis(erin, pid)
    assert a["net_worth"]["net_worth"] == 300000 and a["net_worth"]["breakdown"]["Bank balances"] == 300000
    assert a["liquidity"]["emergency_pool"] == 300000 and a["liquidity"]["runway_months"] is None   # expenses unknown -> no runway

    stock = rec(erin, pid, "stocks", {**VALID["stocks"], "quantity": 40, "current_price": 1650})
    a = analysis(erin, pid)
    assert a["net_worth"]["net_worth"] == 300000 + 40 * 1650 and a["allocation"]["allocation"]["Equity"] == 66000
    erin.patch(f"/api/profiles/{pid}/records/stocks/{stock['id']}", json={"current_price": 1700})
    assert analysis(erin, pid)["net_worth"]["net_worth"] == 300000 + 40 * 1700                       # price edit reflected exactly

    card = rec(erin, pid, "credit_cards", {**VALID["credit_cards"], "credit_limit": 100000, "outstanding": 90000, "min_due": 4500})
    a = analysis(erin, pid)
    assert a["net_worth"]["net_worth"] == 300000 + 68000 - 90000
    assert a["credit"]["overall_utilisation_pct"] == 90.0
    assert "CARD_UTIL_4321" in {r["code"] for r in a["recommendations"]}
    assert a["ml"]["credit_risk"]["available"] is False                    # no statements yet: model says so, does not guess

    loan = rec(erin, pid, "loans", {**VALID["loans"], "emi": 15000, "balance": 300000})
    a = analysis(erin, pid)
    assert a["debt"]["total_emi"] == 15000 and a["debt"]["risk_band"] == "unknown"   # income not known yet
    assert a["net_worth"]["total_liabilities"] == 90000 + 300000

    for m in ("08", "09", "10"):
        rec(erin, pid, "income", {"amount": 100000, "source": "Salary", "date": f"2026-{m}-01", "account_id": acct["id"]})
    a = analysis(erin, pid)
    assert a["cash_flow"]["income_known"] and not a["cash_flow"]["spending_known"]
    assert a["cash_flow"]["avg_monthly_income"] == 100000 and a["cash_flow"]["avg_savings_rate_pct"] is None  # not 100%
    assert a["debt"]["emi_to_income_pct"] == 15.0 and a["debt"]["risk_band"] == "low"
    assert a["tax"]["available"] and a["fire"]["available"] is False

    for m in ("08", "09", "10"):
        rec(erin, pid, "transactions", {"date": f"2026-{m}-03", "amount": 25000, "description": "IMPS RENT FLAT OWNER",
                                         "category": "Rent", "account_id": acct["id"]})
        rec(erin, pid, "transactions", {"date": f"2026-{m}-15", "amount": 15000, "description": "EMI BAJAJ FINANCE",
                                         "category": "EMI", "account_id": acct["id"]})
        rec(erin, pid, "transactions", {"date": f"2026-{m}-20", "amount": 10000, "description": "UPI/DR/1/BIGBASKET/ICIC/bigbasket@ybl",
                                         "category": "Groceries", "account_id": acct["id"]})
    a = analysis(erin, pid)
    cf = a["cash_flow"]
    assert cf["spending_known"] and cf["avg_monthly_expenses"] == 50000 and cf["avg_savings_rate_pct"] == 50.0
    assert a["liquidity"]["runway_months"] == round(300000 / 50000, 2)
    assert a["fire"]["available"] and a["fire"]["inputs"]["annual_expenses"] == (50000 - 15000) * 12   # EMIs excluded in retirement
    assert a["health_score"]["score"] is not None and "Savings" in a["health_score"]["pillars"]
    an = a["ml"]["anomaly"]                                       # scored when an approved model is active, else reported as off
    assert (an.get("available") is False and an["model_status"] == "awaiting_approved_model") or an["transactions_scored"] >= 0
    assert a["ml"]["forecast"]["available"] is False                # < 6 months (and no approved forecaster)
    fire_before = a["fire"]

    rec(erin, pid, "sips", {**VALID["sips"], "amount": 20000})
    a = analysis(erin, pid)
    assert a["investments"]["sip_to_income_pct"] == 20.0
    assert a["fire"]["inputs"]["monthly_investment"] == 20000                # no investment transactions -> entered SIPs
    assert a["fire"]["corpus_at_target_age"] > fire_before["corpus_at_target_age"]
    assert a["health_score"]["pillars"]["Investing"] == 100.0

    erin.patch(f"/api/profiles/{pid}", json={"retirement_age_target": 60})
    a2 = analysis(erin, pid)
    assert a2["fire"]["retirement_age_target"] == 60 and a2["fire"]["corpus_at_target_age"] > a["fire"]["corpus_at_target_age"]

    assert "HEALTH_COVER" in {r["code"] for r in a2["recommendations"]}
    prot_before = a2["health_score"]["pillars"]["Protection"]
    rec(erin, pid, "insurance", {"kind": "health", "insurer": "Niva Bupa", "cover": 1000000, "annual_premium": 18000})
    a = analysis(erin, pid)
    assert "HEALTH_COVER" not in {r["code"] for r in a["recommendations"]}
    assert a["health_score"]["pillars"]["Protection"] > prot_before

    pool_before = a["liquidity"]["emergency_pool"]
    rec(erin, pid, "deposits", {**VALID["deposits"], "principal": 100000, "start_date": "2026-10-31"})
    a = analysis(erin, pid)
    assert a["liquidity"]["emergency_pool"] == pool_before + 100000          # started today -> no interest accrued yet

    rec(erin, pid, "goals", {**VALID["goals"], "target_amount": 800000, "current_amount": 200000, "target_date": "2028-10-31"})
    g = analysis(erin, pid)["goals"][0]
    assert g["months_left"] == 24 and g["monthly_needed"] == 25000.0

    rec(erin, pid, "recurring", {**VALID["recurring"], "amount": 600, "frequency": "monthly"})
    c = analysis(erin, pid)["commitments"]
    assert c["parts"]["Recurring payments"] == 600 and c["parts"]["Loan EMIs"] == 15000 and c["parts"]["Active SIPs"] == 20000
    assert c["monthly_total"] == 600 + 15000 + 20000 + 18000 / 12

    erin.delete(f"/api/profiles/{pid}/records/stocks/{stock['id']}")
    erin.delete(f"/api/profiles/{pid}/records/credit_cards/{card['id']}")
    erin.delete(f"/api/profiles/{pid}/records/loans/{loan['id']}")
    a = analysis(erin, pid)
    assert "Equity" not in a["net_worth"]["breakdown"] and a["net_worth"]["total_liabilities"] == 0
    assert "CARD_UTIL_4321" not in {r["code"] for r in a["recommendations"]}


def test_model_outputs_follow_the_entered_data(erin):
    """Anomaly and forecast models run on the person's own entered transactions."""
    pid = new_private(erin, "Models")
    acct = rec(erin, pid, "bank_accounts", VALID["bank_accounts"])["id"]
    for m in range(4, 11):
        rec(erin, pid, "income", {"amount": 90000, "source": "Salary", "date": f"2026-{m:02d}-01", "account_id": acct})
        for d, amt, desc in [(3, 22000, "IMPS RENT FLAT"), (8, 600 + m * 10, "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment"),
                             (14, 3200, "UPI/DR/1/BIGBASKET/ICIC/bigbasket@ybl/Payment"), (22, 350 + m, "UPI/DR/1/UBER/AXIS/uber@okaxis/Payment"),
                             (11, 2500 + m * 50, "POS 4521XXXXXXXX1234 AMAZON BANGALORE")]:   # a normal monthly Shopping habit
            rec(erin, pid, "transactions", {"date": f"2026-{m:02d}-{d:02d}", "amount": amt, "description": desc, "account_id": acct})
    a = analysis(erin, pid)
    fc = a["ml"]["forecast"]
    if "forecast" in PV.active():
        assert fc["available"] and fc["expected_income"] is not None
    else:                                                         # the trained forecaster failed its baseline: explicitly off
        assert fc["available"] is False and fc["model_status"] == "awaiting_approved_model"
    assert a["ml"]["peers"]["available"] and a["ml"]["peers"]["comparison"]    # 8 ratios computed from the entered records
    assert a["ml"]["credit_risk"]
    big = rec(erin, pid, "transactions", {"date": "2026-10-25", "amount": 48000, "description": "POS 4521XXXXXXXX1234 MYNTRA MUMBAI",
                                          "account_id": acct})
    # The real-data anomaly model (trained on Oklahoma cardholder histories) applied to THIS person's entered transactions,
    # whether or not it is activated: a purchase ~16x their usual Shopping amount must be flagged with a high severity.
    from app.ml import anomaly
    from app.services.loader import load_identity
    art = latest_trained("anomaly")
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        out = anomaly.analyse(art, load_identity(db, uid))
    hit = [f for f in out["flagged"] if f["amount"] == 48000]
    with SessionLocal() as db:
        cats = db.scalars(select(M.Transaction.category).where(M.Transaction.user_id == uid, M.Transaction.type == "debit")).all()
    assert out["transactions_scored"] == sum(c not in anomaly.NOT_SCORED for c in cats)   # every scoreable entry is scored
    assert hit and hit[0]["severity"] == "high"
    assert out["flagged_count"] <= 3                              # the ordinary monthly habit is not flagged wholesale
    a = analysis(erin, pid)
    codes = {r["code"] for r in a["recommendations"]}
    if "anomaly" in PV.active():
        assert "VERIFY_TXN" in codes and any(f["amount"] == 48000 for f in a["ml"]["anomaly"]["flagged"])
    else:                                                         # an unapproved model never drives a recommendation
        assert "VERIFY_TXN" not in codes and a["ml"]["anomaly"]["available"] is False
    erin.delete(f"/api/profiles/{pid}/records/transactions/{big['id']}")
    with SessionLocal() as db:
        out = anomaly.analyse(art, load_identity(db, uid))
    assert not any(f["amount"] == 48000 for f in out["flagged"])  # deleting the entry removes the flag


def test_reports_export_chat_and_planners_use_manual_data(erin):
    pid = new_private(erin, "Outputs")
    acct = rec(erin, pid, "bank_accounts", {**VALID["bank_accounts"], "balance": 123456})["id"]
    rec(erin, pid, "other_assets", {"kind": "epf", "value": 400000})
    nw = 123456 + 400000
    z = zipfile.ZipFile(io.BytesIO(erin.get(f"/api/profiles/{pid}/export.zip").content))
    nwcsv = z.read("net_worth.csv").decode()
    assert "Retirement (EPF/PPF/NPS),400000" in nwcsv and "Bank balances,123456" in nwcsv
    ans = erin.post(f"/api/profiles/{pid}/chat", json={"message": "What is my net worth?", "use_llm": False}).json()["answer"]
    assert "5.23 L" in ans                                                  # ₹5,23,456
    pdf = erin.get(f"/api/profiles/{pid}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    d = erin.post(f"/api/profiles/{pid}/decision", json={"price": 600000}).json()
    assert d["available"] is False and "income records" in d["missing"]
    f = erin.post(f"/api/profiles/{pid}/fire", json={}).json()
    assert f["available"] is False and f["inputs"]["current_corpus"] == 400000
    f = erin.post(f"/api/profiles/{pid}/fire", json={"annual_expenses": 600000, "monthly_investment": 20000}).json()
    assert f["available"] and f["expenses_source"] == "entered by you for this projection" and f["fire_number"] > 0
    b = erin.get(f"/api/profiles/{pid}/briefing", params={"use_llm": False}).json()["briefing"]
    assert "no income or spending history" in b.lower() and "Still missing" in b
    for m in ("09", "10"):
        rec(erin, pid, "income", {"amount": 80000, "source": "Salary", "date": f"2026-{m}-01", "account_id": acct})
        rec(erin, pid, "transactions", {"date": f"2026-{m}-05", "amount": 30000, "description": "IMPS RENT FLAT", "category": "Rent",
                                         "account_id": acct})
    d = erin.post(f"/api/profiles/{pid}/decision", json={"price": 600000, "down_payment": 100000, "item_type": "car"}).json()
    assert d["available"] and d["plan"]["impact"]["monthly_surplus"]["before"] == 50000


def test_sandbox_has_the_same_manual_entry_features(erin):
    """Demo sandboxes and private profiles have identical abilities."""
    sb = erin.post("/api/demo/explore", json={"template_id": "FINORA_USER_001"}).json()["profile"]["internal_id"]
    before = analysis(erin, sb)["net_worth"]["net_worth"]
    st = rec(erin, sb, "stocks", {**VALID["stocks"], "quantity": 10, "current_price": 1000})
    assert analysis(erin, sb)["net_worth"]["net_worth"] == pytest.approx(before + 10000, abs=0.01)
    assert erin.delete(f"/api/profiles/{sb}/records/stocks/{st['id']}").status_code == 200
    assert analysis(erin, sb)["net_worth"]["net_worth"] == pytest.approx(before, abs=0.01)
    counts = erin.get(f"/api/profiles/{sb}/records").json()
    assert counts["transactions"] > 300 and counts["credit_cards"] >= 1


def test_profile_details_validation(erin):
    pid = new_private(erin, "Details", age=40, retire=60)
    assert erin.patch(f"/api/profiles/{pid}", json={"retirement_age_target": 35}).status_code == 422   # below current age
    assert erin.patch(f"/api/profiles/{pid}", json={"age": 70}).status_code == 422                     # above target
    assert erin.patch(f"/api/profiles/{pid}", json={"pan_hash": "x"}).status_code == 422                # not editable
    r = erin.patch(f"/api/profiles/{pid}", json={"name": "Renamed Person", "employment_type": "self_employed"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed Person"
    assert analysis(erin, pid)["profile"]["employment_type"] == "self_employed"

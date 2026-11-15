"""Phase 9: verification and evidence.

Targeted checks that complement the existing suites (test_auth, test_route_security, test_records, test_statement_*,
test_cfo_*). Nothing here adds a feature; each test probes an existing behaviour end to end through the real API.

1. Ownership sweep: EVERY profile-scoped route is called by a second account
   a) with the victim's profile id                         -> 404 (never 2xx, never 500)
   b) with its OWN profile id but the victim's child ids   -> 404 (second-level IDOR: tx, goal, import, rule, rec, assumption)
   c) with no session                                      -> 401
   and the victim's data is compared before/after: nothing was read, changed or deleted.
2. Financial calculations: goals (0% / 7%, reached, overdue, invalid inputs), debt payoff (incl. a payment that never
   covers the interest), FIRE and what-if input validation and formulas.
3. Statement import: unsupported formats are refused and leave nothing behind.
4. The six ML features answer through their real endpoints with provenance.
"""
import io
import math
import re
from datetime import date

import pytest
from sqlalchemy import select, update

from app import models as M
from app.database import SessionLocal
from app.services.calculations import AS_OF

from .conftest import TestClient, app, signed_in_client
from .test_route_security import _routes

CSV = ("Date,Narration,Withdrawal,Deposit\n"
       "05/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,450,\n"
       "06/10/2026,UPI/DR/1/UBER/AXIS/uber@okaxis/Payment,250,\n"
       "07/10/2026,NEFT CR SALARY ACME LTD,,90000\n").encode()


def _months_ahead(n):
    y, m = divmod(AS_OF.month - 1 + n, 12)
    return date(AS_OF.year + y, m + 1, 1)


def _private(c, name="Phase Nine"):
    r = c.post("/api/profiles", json={"name": name, "age": 32, "retirement_age_target": 55, "city": "Pune"})
    assert r.status_code == 200, r.text
    return r.json()["profile"]["internal_id"]


def _rec(c, pid, typ, body):
    r = c.post(f"/api/profiles/{pid}/records/{typ}", json=body)
    assert r.status_code == 201, (typ, r.text)
    return r.json()


# ================================================================ 1. ownership sweep
@pytest.fixture(scope="module")
def victim():
    c = signed_in_client("p9victim")
    pid = _private(c, "Victim Person")
    acc = _rec(c, pid, "bank_accounts", {"bank_name": "HDFC Bank", "account_type": "salary", "last4": "1234", "balance": 50000})
    _rec(c, pid, "income", {"amount": 90000, "source": "Salary", "date": "2026-10-01"})
    goal = _rec(c, pid, "goals", {"name": "Car", "target_amount": 800000, "target_date": "2028-10-31", "current_amount": 200000})
    tx = _rec(c, pid, "transactions", {"date": "2026-10-05", "amount": 640, "description": "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment"})
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("v.csv", io.BytesIO(CSV), "text/csv")})
    assert pv.status_code == 201, pv.text
    assert c.post(f"/api/profiles/{pid}/imports/{pv.json()['id']}/start", json={"account_id": acc["id"]}).status_code == 202
    assert c.post(f"/api/profiles/{pid}/chat", json={"message": "What is my net worth?", "use_llm": False}).status_code == 200
    assert c.get(f"/api/profiles/{pid}/report.pdf").status_code == 200
    a = c.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": "sip", "params": {"amount": 1000}})
    assert a.status_code in (200, 201), a.text
    recs = c.get(f"/api/profiles/{pid}/recommendations").json()
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        rule = M.CategoryRule(user_id=uid, merchant_key="swiggy", category="Dining")
        db.add(rule)
        db.commit()
        rule_id = rule.id
    sandbox = c.post("/api/demo/explore", json={"template_id": "FINORA_USER_001"}).json()["profile"]["internal_id"]
    c.pid, c.sandbox = pid, sandbox
    c.ids = {"tx_id": tx["id"], "item_id": goal["id"], "record_type": "goals", "imp_id": pv.json()["id"], "rule_id": rule_id,
             "rec_id": recs[0]["id"] if recs else 999999, "aid": a.json()["id"], "code": "EMERGENCY_FUND"}
    return c


def _snapshot(c, pid):
    """Everything the victim owns, as the victim sees it."""
    get = lambda p: c.get(f"/api/profiles/{pid}{p}").json()  # noqa: E731
    return {"profile": get(""), "records": get("/records"), "tx": get("/transactions?page_size=500"), "imports": get("/imports"),
            "chat": get("/chat"), "reports": get("/reports"), "rules": get("/category-rules"), "recs": get("/recommendations"),
            "plan": c.get(f"/api/profiles/{pid}/plan").json().get("assumptions")}


BODIES = {   # valid-looking bodies so a 404 means "not yours", not "bad input"
    "transactions/{tx_id}": {"category": "Dining"}, "records/{record_type}/{item_id}": {"current_amount": 1},
    "recommendations/{rec_id}": {"status": "accepted"}, "plan/assumptions/{aid}": {"params": {"amount": 2000}},
    "suggestion": {"action": "accept"}, "records/{record_type}": {"name": "Hack", "target_amount": 1, "target_date": "2030-01-01"},
    "transactions": {"date": "2026-10-05", "amount": 1, "description": "HACK"}, "chat": {"message": "hi", "use_llm": False},
    "chat/stream": {"message": "hi", "use_llm": False}, "decision": {"price": 1000}, "plan/dismiss": {"code": "X"},
    "plan/preview": {"assumptions": []}, "review/confirm": {"items": [{"kind": "tx", "id": 1}]},
    "review/classify": {"items": [{"kind": "tx", "id": 1, "category": "Dining"}]}, "plan/assumptions": {"kind": "sip", "params": {"amount": 1}},
}


def _call(c, method, path, ids, pid):
    url = path.replace("{internal_id}", pid)
    for k, v in ids.items():
        url = url.replace("{" + k + "}", str(v))
    tail = path.split("{internal_id}/")[-1] if "{internal_id}/" in path else ""
    kw = {}
    if method in ("POST", "PATCH", "PUT"):
        if tail in ("upload", "imports"):
            kw["files"] = {"file": ("s.csv", io.BytesIO(CSV), "text/csv")}
        else:
            key = next((k for k in BODIES if tail == k or tail.endswith("/" + k)), None)
            kw["json"] = BODIES.get(key, {})
    return getattr(c, method.lower())(url, **kw)


PROFILE_ROUTES = sorted({(m, p) for m, p, _ in _routes() if "{internal_id}" in p and m != "HEAD"})
CHILD = re.compile(r"\{(tx_id|item_id|imp_id|rule_id|rec_id|aid)\}")


def test_sweep_covers_the_whole_profile_api():
    assert len(PROFILE_ROUTES) >= 50
    assert sum(1 for _, p in PROFILE_ROUTES if CHILD.search(p)) >= 10


def test_another_account_gets_404_on_every_profile_route_and_nothing_changes(victim):
    before = _snapshot(victim, victim.pid)
    mallory = signed_in_client("p9mallory")
    bad = []
    for target in (victim.pid, victim.sandbox):
        for m, p in PROFILE_ROUTES:
            r = _call(mallory, m, p, victim.ids, target)
            if r.status_code != 404:
                bad.append((m, p, target == victim.sandbox, r.status_code))
    assert not bad, bad
    assert _snapshot(victim, victim.pid) == before


def test_own_profile_id_with_another_accounts_child_ids_is_404(victim):
    before = _snapshot(victim, victim.pid)
    mallory = signed_in_client("p9mallory2")
    own = _private(mallory, "Mallory Own")
    bad = []
    for m, p in PROFILE_ROUTES:
        if not CHILD.search(p):
            continue
        r = _call(mallory, m, p, victim.ids, own)
        if r.status_code != 404:
            bad.append((m, p, r.status_code, r.text[:80]))
    assert not bad, bad
    assert _snapshot(victim, victim.pid) == before


def test_no_session_gets_401_on_every_profile_route(victim):
    anon = TestClient(app)
    bad = [(m, p, r.status_code) for m, p in PROFILE_ROUTES if (r := _call(anon, m, p, victim.ids, victim.pid)).status_code != 401]
    assert not bad, bad


def test_templates_are_readable_but_every_write_is_403():
    c = signed_in_client("p9tpl")
    bad = []
    for m, p in PROFILE_ROUTES:
        if m == "GET" or CHILD.search(p):
            continue
        r = _call(c, m, p, {"record_type": "goals", "code": "X"}, "FINORA_USER_001")
        # read-only computations (what-ifs, chat on own history, analyse) are allowed on templates; everything else must be 403
        ok = r.status_code == 403 or (r.status_code in (200, 201, 202) and p.split("{internal_id}/")[-1] in
                                      ("analyze", "fire", "decision", "payoff", "chat", "chat/stream", "plan/preview"))
        if not ok:
            bad.append((m, p, r.status_code))
    assert not bad, bad


def test_signed_out_session_cannot_be_reused_on_profile_data(victim):
    c = signed_in_client("p9logout")
    pid = _private(c)
    cookies = dict(c.cookies)
    assert c.post("/api/auth/logout").status_code == 200
    replay = TestClient(app, cookies=cookies)
    assert replay.get(f"/api/profiles/{pid}").status_code == 401
    assert replay.get(f"/api/profiles/{pid}/transactions").status_code == 401


# ================================================================ 2. financial calculations
@pytest.fixture(scope="module")
def gina():
    c = signed_in_client("p9gina")
    c.pid = _private(c, "Gina Goals")
    return c


def _goals(c):
    return {g["name"]: g for g in c.get(f"/api/profiles/{c.pid}/analysis").json()["goals"]}


def test_goal_monthly_amounts_at_0_and_7_percent(gina):
    target = _months_ahead(12)
    _rec(gina, gina.pid, "goals", {"name": "Trip", "target_amount": 120000, "target_date": target.isoformat(), "current_amount": 0})
    g = _goals(gina)["Trip"]
    months = (target.year - AS_OF.year) * 12 + target.month - AS_OF.month
    assert g["months_left"] == months
    assert g["monthly_needed"] == pytest.approx(120000 / months, abs=0.01)                        # 0% growth
    i = 0.07 / 12
    assert g["monthly_needed_at_7pct"] == pytest.approx(120000 * i / ((1 + i) ** months - 1), abs=0.01)  # 7% assumed
    assert g["monthly_needed_at_7pct"] < g["monthly_needed"]
    assert g["progress_pct"] == 0 and g["reached"] is False and g["overdue"] is False


def test_goal_progress_reached_and_overdue(gina):
    _rec(gina, gina.pid, "goals", {"name": "Laptop", "target_amount": 100000, "target_date": "2027-06-30", "current_amount": 25000})
    _rec(gina, gina.pid, "goals", {"name": "Done", "target_amount": 50000, "target_date": "2027-06-30", "current_amount": 50000})
    late = _rec(gina, gina.pid, "goals", {"name": "Late", "target_amount": 60000, "target_date": "2027-06-30", "current_amount": 10000})
    with SessionLocal() as db:                       # time passes: a goal's date can fall behind "today" after it was created
        db.execute(update(M.Goal).where(M.Goal.id == late["id"]).values(target_date=date(2026, 6, 30)))
        db.commit()
    gina.post(f"/api/profiles/{gina.pid}/analyze")
    gs = _goals(gina)
    assert gs["Laptop"]["progress_pct"] == 25.0 and not gs["Laptop"]["reached"] and not gs["Laptop"]["overdue"]
    assert gs["Done"]["progress_pct"] == 100.0 and gs["Done"]["reached"] and gs["Done"]["monthly_needed"] == 0
    assert gs["Late"]["overdue"] and not gs["Late"]["reached"]
    assert gs["Late"]["monthly_needed"] == 50000     # the whole gap is still needed; the UI says "target date passed"


@pytest.mark.parametrize("bad", [{"target_amount": 0}, {"target_amount": -5}, {"current_amount": -1}, {"target_date": "2020-01-01"},
                                 {"target_date": AS_OF.isoformat()}, {"name": "X"}])
def test_goal_invalid_inputs_are_refused(gina, bad):
    body = {"name": "Bad goal", "target_amount": 1000, "target_date": "2028-01-01", "current_amount": 0, **bad}
    assert gina.post(f"/api/profiles/{gina.pid}/records/goals", json=body).status_code == 422


def test_payoff_matches_the_loan_and_reports_a_debt_that_is_never_paid_off():
    c = signed_in_client("p9debt")
    pid = _private(c, "Debt Person")
    assert c.post(f"/api/profiles/{pid}/payoff", json={}).json() == {"has_debt": False}
    assert c.post(f"/api/profiles/{pid}/payoff", json={"extra_monthly": -1}).status_code == 422
    loan = _rec(c, pid, "loans", {"loan_type": "Personal Loan", "lender": "Bajaj Finance", "principal": 500000, "balance": 300000,
                                  "emi": 15000, "interest_rate": 14, "tenure_months": 36, "remaining_months": 22})
    p = c.post(f"/api/profiles/{pid}/payoff", json={}).json()
    # 300,000 at 14% with a 15,000 EMI: the standard amortisation gives n = -ln(1 - P*i/EMI) / ln(1+i)
    i = 0.14 / 12
    n = -math.log(1 - 300000 * i / 15000) / math.log(1 + i)
    assert p["avalanche"]["paid_off"] and p["avalanche"]["months_to_debt_free"] == math.ceil(n)
    assert p["avalanche"]["total_interest"] == pytest.approx(15000 * n - 300000, rel=0.02)
    more = c.post(f"/api/profiles/{pid}/payoff", json={"extra_monthly": 10000}).json()
    assert more["avalanche"]["months_to_debt_free"] < p["avalanche"]["months_to_debt_free"]
    assert more["vs_no_extra"]["months_saved"] > 0 and more["vs_no_extra"]["interest_saved"] > 0
    # an EMI below the monthly interest (300,000 x 14% / 12 = 3,500) never clears the loan
    assert c.patch(f"/api/profiles/{pid}/records/loans/{loan['id']}", json={"emi": 2000}).status_code == 200
    never = c.post(f"/api/profiles/{pid}/payoff", json={}).json()
    # before the Phase 9 fix this reported "debt-free in 600 months" with Rs 13.6 crore of interest
    assert never["avalanche"]["paid_off"] is False and never["avalanche"]["never_paid_off"] == ["Personal Loan (Bajaj Finance)"]
    assert never["interest_saved_by_avalanche"] is None and never["vs_no_extra"] is None
    ln = c.get(f"/api/profiles/{pid}/analysis").json()["debt"]["loans"][0]
    assert ln["never_paid_off"] is True and ln["remaining_interest"] is None   # was EMI x months - balance, meaningless here
    plan = c.get(f"/api/profiles/{pid}/plan").json()
    for act in plan.get("actions", []):                  # no action claims a crore-scale "interest saved" against a never-cleared debt
        inr_ = (act.get("impact") or {}).get("inr")
        assert inr_ is None or abs(inr_) < 1e7, (act.get("kind"), inr_)
        assert (act.get("effect") or {}).get("debt_interest") is None or abs(act["effect"]["debt_interest"]) < 1e7
    enough = c.post(f"/api/profiles/{pid}/payoff", json={"extra_monthly": 10000}).json()
    assert enough["avalanche"]["paid_off"] is True and enough["vs_no_extra"] is None   # no honest baseline to compare with
    # the AI CFO's debt tool and writer state it instead of quoting the capped numbers
    from app.cfo import tools, writer
    from app.routes import common
    with SessionLocal() as db:
        user = db.scalar(select(M.User).where(M.User.internal_id == pid))
        f = tools.debts_and_payoff(common.cfo_context(db, user))
    assert f["paid_off"] is False and f["avalanche_months"] is None and f["avalanche_interest"] is None
    assert "never paid off" in writer._w_debt({**f, "has_debt": True})


def test_fire_formula_and_validation():
    c = signed_in_client("p9fire")
    pid = _private(c, "Fire Person")
    empty = c.post(f"/api/profiles/{pid}/fire", json={}).json()
    assert empty["available"] is False and "annual_expenses" in empty["needs"]       # nothing invented without expenses
    r = c.post(f"/api/profiles/{pid}/fire", json={"annual_expenses": 600000, "monthly_investment": 20000, "withdrawal_rate_pct": 4}).json()
    assert r["available"] and r["fire_number"] == 15_000_000                          # expenses / withdrawal rate
    assert r["expenses_source"] == "entered by you for this projection"
    more = c.post(f"/api/profiles/{pid}/fire", json={"annual_expenses": 600000, "monthly_investment": 60000, "withdrawal_rate_pct": 4}).json()
    assert more["fire_age"] is None or r["fire_age"] is None or more["fire_age"] <= r["fire_age"]
    for bad in ({"annual_expenses": 0}, {"monthly_investment": -1}, {"withdrawal_rate_pct": 1}, {"nominal_return_pct": 50},
                {"retirement_age": 20}, {"current_corpus": -10}):
        assert c.post(f"/api/profiles/{pid}/fire", json=bad).status_code == 422, bad


def test_what_if_validation_and_emi():
    c = signed_in_client("p9whatif")
    pid = _private(c, "Whatif Person")
    nodata = c.post(f"/api/profiles/{pid}/decision", json={"price": 600000}).json()
    assert nodata["available"] is False and nodata["missing"]                         # no verdict without income and spending
    for bad in ({"price": 0}, {"price": -1}, {"price": 1000, "down_payment": -1}, {"price": 1000, "interest_rate": 99},
                {"price": 1000, "tenure_months": 999}):
        assert c.post(f"/api/profiles/{pid}/decision", json=bad).status_code == 422, bad
    d = c.post("/api/profiles/FINORA_USER_001/decision", json={"price": 600000, "down_payment": 100000, "interest_rate": 9, "tenure_months": 60}).json()
    i = 0.09 / 12
    assert d["plan"]["emi"] == pytest.approx(500000 * i * (1 + i) ** 60 / ((1 + i) ** 60 - 1), abs=1)
    cash = c.post("/api/profiles/FINORA_USER_001/decision", json={"price": 600000, "down_payment": 600000, "tenure_months": 0}).json()
    assert cash["plan"]["emi"] == 0
    assert d["plan"]["verdict"] in ("AFFORDABLE", "STRETCH", "NOT ADVISABLE")


def test_cash_flow_forecast_is_honest_without_history():
    c = signed_in_client("p9fc")
    pid = _private(c, "No History")
    fc = c.get(f"/api/profiles/{pid}/analysis").json()["ml"]["forecast"]
    assert fc["available"] is False and "history" in fc["note"]                       # never a forecast from no data
    demo = c.get("/api/profiles/FINORA_USER_001/analysis").json()["ml"]["forecast"]
    assert demo["available"]
    assert demo["range"]["low"] <= demo["predicted_total_expense"] <= demo["range"]["high"]   # the point sits inside its range
    assert demo["three_month_avg"] > 0                                                # shown beside a 3-month average


# ================================================================ 3. statement import edge cases
@pytest.mark.parametrize("name,content,ctype", [
    ("statement.pdf", b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF", "application/pdf"),
    ("statement.xlsx", b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png"),
    ("missing.csv", b"Date,Narration\n05/10/2026,SWIGGY\n", "text/csv"),                 # no amount column
])
def test_unsupported_or_incomplete_files_are_refused_and_leave_nothing(name, content, ctype):
    c = signed_in_client("p9imp")
    pid = _private(c, "Import Edge")
    r = c.post(f"/api/profiles/{pid}/imports", files={"file": (name, io.BytesIO(content), ctype)})
    assert r.status_code == 422 and "header row" in r.json()["detail"]                  # refused with the reason
    assert c.get(f"/api/profiles/{pid}/imports").json()["items"] == []                   # no half-created import
    assert c.get(f"/api/profiles/{pid}/transactions").json()["total"] == 0


def test_import_and_undo_belong_to_the_signed_in_account():
    c = signed_in_client("p9undo")
    pid = _private(c, "Undo Person")
    acc = _rec(c, pid, "bank_accounts", {"bank_name": "HDFC Bank", "account_type": "salary", "last4": "1234", "balance": 50000})
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("s.csv", io.BytesIO(CSV), "text/csv")}).json()
    c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": acc["id"]})
    s = c.get(f"/api/profiles/{pid}/imports/{pv['id']}").json()["summary"]
    assert s["transactions_added"] == 2 and s["income_records_added"] == 1 and s["rows_dropped"] == 0   # salary credit -> income
    assert c.get(f"/api/profiles/{pid}/transactions").json()["total"] == 2
    assert c.get(f"/api/profiles/{pid}/records/income").json()["total"] == 1
    with SessionLocal() as db:
        owner = db.scalar(select(M.User.owner_id).where(M.User.internal_id == pid))
        imp = db.get(M.StatementImport, pv["id"])
        assert imp.user_id == db.scalar(select(M.User.id).where(M.User.internal_id == pid)) and owner is not None
    assert c.delete(f"/api/profiles/{pid}/imports/{pv['id']}").status_code == 200
    assert c.get(f"/api/profiles/{pid}/transactions").json()["total"] == 0
    assert c.get(f"/api/profiles/{pid}/records/income").json()["total"] == 0              # undo removes everything it added


# ================================================================ 4. the six ML features, through their real endpoints
def test_six_ml_features_answer_with_their_real_models(client):
    lab = client.get("/api/models/lab").json()
    text = str(lab).lower()
    for algo in ("xgboost", "k-means", "tf-idf", "isolation forest"):
        assert algo in text, algo
    a = client.get("/api/profiles/FINORA_USER_001/analysis").json()["ml"]
    for k in ("credit_risk", "anomaly", "forecast", "peers"):
        assert a[k]["model_info"]["version"].startswith("v"), k                       # every output names its model version
    # 1 credit risk: probability per card + SHAP contributions per input
    cr = a["credit_risk"]
    assert 0 <= cr["overall_default_probability_pct"] <= 100 and cr["cards"]
    for card in cr["cards"]:
        assert 0 <= card["default_probability_pct"] <= 100
        assert card["top_factors"] and all(isinstance(f["shap"], float) and f["effect"] in ("raises risk", "lowers risk") for f in card["top_factors"])
        assert all((f["shap"] > 0) == (f["effect"] == "raises risk") for f in card["top_factors"])
    assert client.post("/api/models/credit-risk/score", json={}).status_code == 422   # invalid input refused, not guessed
    # 2 peers: a peer group and percentiles that are percentages
    pe = a["peers"]
    assert pe["available"] and pe["peer_group"] and pe["comparison"]
    assert all(0 <= m["better_than_pct_of_people"] <= 100 for m in pe["comparison"])
    # 3 categoriser: category + confidence from free text; low confidence is flagged for review, never silently applied
    cat = client.post("/api/categorise", json={"texts": ["UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment", "NEFT CR SALARY ACME LTD"]}).json()
    assert len(cat) == 2 and all(x["category"] and 0 <= x["confidence"] <= 1 and x["source"] in ("model", "rule") for x in cat)
    assert all(x["needs_review"] for x in cat if x["source"] == "model" and x["confidence"] < 0.5)
    assert client.post("/api/categorise", json={"text": "x"}).status_code == 422
    # 4 anomaly: every flag has a score and human-readable reasons measured against the person's own history
    an = a["anomaly"]
    assert an["transactions_scored"] > 0 and an["flagged_count"] == len(an["flagged"]) or an["flagged_count"] >= len(an["flagged"])
    assert all(f["reasons"] and 0 <= f["anomaly_score"] <= 1 and f["typical_amount"] > 0 for f in an["flagged"])
    # 5 forecast: checked in test_cash_flow_forecast_is_honest_without_history
    # 6 model lab: versions, datasets, training runs and metrics are served
    assert client.get("/api/models/metrics").status_code == 200


def test_plan_never_claims_interest_saved_against_a_debt_that_is_never_cleared(analyses):
    """Before the fix: baseline interest was the 600-month capped total (crores), so an extra-repayment action showed
    'interest saved: Rs 13.6 crore' and ranked first. Now the baseline has no interest total and the action says what it does."""
    from dataclasses import replace
    from app.services import plan as PL
    b = PL.base_from(analyses["FINORA_USER_001"], [])
    b = replace(b, debts=[{"name": "Personal Loan (Bajaj Finance)", "balance": 300000, "rate": 14, "payment": 2000}])
    base = PL.evaluate(b, [])
    scen = PL.evaluate(b, [{"kind": "extra_debt_repayment", "params": {"amount": 10000}}])
    assert base["debt_free_months"] is None and base["debt_interest"] is None
    assert scen["debt_free_months"] and scen["debt_interest"] is not None and scen["debt_interest"] < 300000
    delta = PL.compare(base, scen)
    assert delta["debt_interest"] is None
    imp = PL.headline_impact("extra_debt_repayment", {"amount": 10000}, delta)
    assert imp["inr"] is None and "never paid off" in imp["label"]
    assert abs(PL.benefit(delta, base, scen)) < 1000          # no crore-scale ranking boost

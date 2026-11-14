"""Phase 6: real-data models only, explicit activation, no silent synthetic fallback, blinded human review.

All of this runs against the suite's temporary COPY of artifacts/ (conftest), never the real folder.
"""
import json
import shutil

import pytest

from app.ml import categoriser, provenance as PV, registry
from app.ml.data import pcard as PC
from app.ml.real import anomaly_review_eval as EV
from app.routes.review import cohen_kappa
from .conftest import signed_in_client


# ---------------------------------------------------------------- registry and activation
def test_only_activated_real_models_load_and_legacy_is_not_a_fallback():
    act = PV.active()
    for n in registry.NAMES:
        if n in act:
            art = registry.get(n)
            assert art is not None
            assert act[n]["path"].startswith("real/")
        else:
            with pytest.raises(registry.ModelUnavailable):
                registry.get(n)
    assert (registry.LEGACY_DIR / "README.md").exists()                 # legacy kept, not deleted
    assert all((registry.LEGACY_DIR / f"{n}.joblib").exists() for n in registry.NAMES)
    assert not any((PV.ARTIFACTS_DIR / f"{n}.joblib").exists() for n in registry.NAMES)   # nothing synthetic at top level


def test_every_active_model_has_real_data_provenance():
    for n, e in PV.active().items():
        if n == "_history":
            continue
        p = registry.provenance(n)
        assert p["data_status"] == "real" and p["approved_by_owner"]
        if e.get("status", "accepted") == "accepted":                 # accepted: evaluated and all criteria met
            from app.ml import acceptance
            passed, _ = acceptance.check(n, PV.load_metrics(PV.REAL_DIR / n / e["version"]))
            assert p["evaluation_passed"] and passed                    # recomputed from the metrics, not trusted from a flag
        else:                                                         # experimental: unmet criteria recorded with a reason
            assert e["status"] == "experimental" and e["unmet_criteria"] and e["experimental_reason"]
        assert p["artifact"]["sha256"] == e["sha256"] == PV.sha256(PV.ARTIFACTS_DIR / e["path"])
        assert p["datasets"] and all(d.get("observations", "real").startswith("real") for d in p["datasets"])
        assert p["environment"]["trained_locally"] and not p["environment"]["remote_services_used"]


def _copy_version(model, version, edit):
    src = PV.REAL_DIR / model / version
    dst = PV.REAL_DIR / model / f"{version}-t"
    shutil.copytree(src, dst, dirs_exist_ok=True)
    prov = json.loads((dst / "provenance.json").read_text())
    prov["artifact"]["path"] = prov["artifact"]["path"].replace(version, f"{version}-t")
    edit(prov, dst)
    (dst / "provenance.json").write_text(json.dumps(prov))
    return f"{version}-t", dst


@pytest.mark.parametrize("field,value", [("data_status", "synthetic"), ("evaluation_passed", False), ("approved_by_owner", False)])
def test_activation_refuses_unapproved_or_synthetic(field, value):
    v = PV.active()["credit_risk"]["version"]
    ver, dst = _copy_version("credit_risk", v, lambda p, d: p.__setitem__(field, value))
    try:
        with pytest.raises(RuntimeError, match="not activatable"):
            PV.activate("credit_risk", ver, "test")
    finally:
        shutil.rmtree(dst)
    assert PV.active()["credit_risk"]["version"] == v


def test_activation_refuses_a_tampered_artifact_and_load_refuses_a_checksum_mismatch():
    v = PV.active()["credit_risk"]["version"]
    ver, dst = _copy_version("credit_risk", v, lambda p, d: (d / "model.joblib").write_bytes(b"tampered"))
    try:
        with pytest.raises(RuntimeError, match="checksum"):
            PV.activate("credit_risk", ver, "test")
    finally:
        shutil.rmtree(dst)
    before = PV.ACTIVE.read_text()
    try:
        act = json.loads(before)
        act["credit_risk"]["sha256"] = "0" * 64
        PV.ACTIVE.write_text(json.dumps(act))
        registry.reload()
        with pytest.raises(registry.ModelUnavailable, match="checksum"):
            registry.get("credit_risk")
    finally:
        PV.ACTIVE.write_text(before)
        registry.reload()


def test_activation_keeps_rollback_history():
    v = PV.active()["credit_risk"]["version"]
    before = PV.ACTIVE.read_text()
    try:
        PV.activate("credit_risk", v, "re-activate for the test")
        hist = PV.active()["_history"]
        assert hist[-1]["model"] == "credit_risk" and hist[-1]["previous"]["version"] == v
    finally:
        PV.ACTIVE.write_text(before)


# ---------------------------------------------------------------- API
def test_model_lab_reports_status_provenance_and_the_ai_cfo_discrepancy(client):
    lab = client.get("/api/models/lab").json()
    names = [m["name"] for m in lab["models"]]
    assert names == registry.NAMES + ["anomaly_ulb_benchmark"]
    for m in lab["models"]:
        assert m["status"] in registry.STATUS_TEXT
        if m["active"]:
            assert m["provenance"]["data_status"] == "real" and m["label"]
    fc = next(m for m in lab["models"] if m["name"] == "forecast")
    if fc["provenance"]:
        assert fc["acceptance"]["passed"] is False and fc["status"] in ("experimental", "trained_not_active")
        assert fc["activation_status"] in (None, "experimental")       # never accepted while it loses to the baseline
        assert "ONE real UK person" in fc["label"]
    ulb = next(m for m in lab["models"] if m["name"] == "anomaly_ulb_benchmark")
    assert ulb["status"] in ("benchmark", "awaiting_training") and not ulb["active"]
    assert lab["ai_cfo"]["trained_by_finora"] is False and lab["ai_cfo"]["installed_tag"] == "qwen2.5:3b"


def test_retraining_through_the_api_is_gone(client):
    r = client.post("/api/models/retrain")
    assert r.status_code in (403, 410)


def test_categorise_without_a_model_never_invents_a_category(monkeypatch):
    def unavailable(name):
        raise registry.ModelUnavailable("awaiting")
    monkeypatch.setattr(registry, "get", unavailable)
    out = categoriser.safe_predict(["SOME UNKNOWN MERCHANT 123", "NACH/DR/BAJAJ FINANCE EMI/88213344", "ATM WDL HDFC ATM JAIPUR"])
    assert out[0] == {"category": None, "confidence": None, "needs_review": True, "source": "none"}
    assert out[1]["category"] == "EMI" and out[1]["source"] == "rule"
    assert out[2]["category"] == "Cash" and out[2]["source"] == "rule"


@pytest.mark.parametrize("text,cat", [("NACH/DR/BAJAJ FINANCE EMI/88213344", "EMI"), ("ATM WDL HDFC ATM JAIPUR", "Cash"),
                                      ("ACH D- BSE LTD-PARAG PARIKH FLEXI", "Investment"), ("CREDIT CARD PAYMENT HDFC CARD", "Card Payment")])
def test_bank_side_categories_are_rules(text, cat):
    assert categoriser.bank_side_rule(text) == cat


# ---------------------------------------------------------------- MCC label mapping
@pytest.mark.parametrize("mcc,cat", [
    ("GROCERY STORES, SUPERMARKETS", "Groceries"), ("GROCERY STORES  SUPERMARKETS", "Groceries"),
    ("FAST FOOD RESTAURANTS", "Dining"), ("HOLIDAY INNS", "Travel"), ("AMERICAN AIRLINES", "Travel"),
    ("SERVICE STATIONS", "Fuel"), ("DRUG STORES, PHARMACIES", "Health"), ("CABLE  SATELLITE & OTHER PAY TV/RADIO SE", "Utilities"),
    ("STATIONARY, OFFICE AND SCHOOL SUPPLY STO", "Shopping"), ("COLLEGES, UNIVERSITIES, PROFESSIONAL SCH", "Education"),
    ("LAB/MEDICAL/DENTAL/OPHTHALMIC HOSPITAL E", None),        # equipment supplier, not personal health care
    ("INDUSTRIAL SUPPLIES NOT ESLEWHERE CLASSI", None), ("GOVERNMENT SERVICES NOT ELSEWHERE CLASSI", None),
    ("RECREATIONAL AND UTILITY TRAILER, CAMPER", None), ("TAX PAYMENTS", None),
])
def test_mcc_mapping_is_explicit_and_excludes_non_personal_codes(mcc, cat):
    assert PC.map_mcc(mcc) == cat


def test_merchant_grouping_removes_store_numbers():
    assert PC.merchant_group("STARBUCKS STORE 01234") == PC.merchant_group("STARBUCKS STORE 99881") == "STARBUCKS STORE"


# ---------------------------------------------------------------- blinded human review
def _sample_exists():
    from app.routes.review import sample_path
    return sample_path() is not None


@pytest.mark.skipif(not _sample_exists(), reason="anomaly model not trained yet")
def test_review_items_are_blinded_and_labels_are_per_reviewer(client):
    a, b = signed_in_client("rev-a"), signed_in_client("rev-b")
    s = a.get("/api/models/anomaly-review").json()
    raw = json.dumps(s["items"])
    for hidden in ("score", "model_flag", "rule_flag", "stratum", "selection_probability", "S1_", "S2_", "S3_"):
        assert hidden not in raw
    assert s["done"] == 0 and len(s["items"]) == s["total"] > 0
    first = s["items"][0]["item_id"]
    assert a.put(f"/api/models/anomaly-review/{first}", json={"label": "very_unusual"}).status_code == 200
    assert a.put(f"/api/models/anomaly-review/{first}", json={"label": "usual"}).status_code == 200      # change, not duplicate
    assert b.put(f"/api/models/anomaly-review/{first}", json={"label": "usual"}).status_code == 200
    assert a.put(f"/api/models/anomaly-review/{first}", json={"label": "fraud"}).status_code == 422
    assert a.put("/api/models/anomaly-review/nope", json={"label": "usual"}).status_code == 404
    assert a.get("/api/models/anomaly-review").json()["items"][0]["your_label"]["label"] == "usual"
    assert b.get("/api/models/anomaly-review").json()["done"] == 1
    prog = a.get("/api/models/anomaly-review/progress").json()
    assert prog["items_with_two_or_more_labels"] >= 1 and "score" not in json.dumps(prog)


@pytest.mark.skipif(not _sample_exists(), reason="anomaly model not trained yet")
def test_review_needs_a_full_signed_in_account():
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/api/models/anomaly-review").status_code == 401


def test_cohen_kappa_and_consensus_arithmetic():
    # arithmetic checks on literal lists; no model, sample or database labels are involved
    assert cohen_kappa(["usual", "usual"], ["usual", "usual"]) is None or cohen_kappa(["usual", "usual"], ["usual", "usual"]) == 1.0
    assert cohen_kappa(["usual", "very_unusual"], ["usual", "very_unusual"]) == 1.0
    assert cohen_kappa(["usual", "very_unusual"], ["very_unusual", "usual"]) == -1.0
    assert EV.consensus(["usual", "very_unusual"]) is None                         # tie -> excluded
    assert EV.consensus(["somewhat_unusual", "very_unusual", "usual"]) == "unusual"
    assert EV.consensus(["cannot_tell"]) is None


def test_recall_is_not_reported_when_the_sample_cannot_support_it():
    design = {"S1_model_flagged": {"population": 100, "sampled": 2, "selection_probability": 0.02},
              "S2_rule_flagged_only": {"population": 1000, "sampled": 1, "selection_probability": 0.001},
              "S3_neither": {"population": 9000, "sampled": 1, "selection_probability": 0.0001}}
    items = [{"item_id": f"r{i}", "stratum": s} for i, s in enumerate(["S1_model_flagged", "S1_model_flagged", "S2_rule_flagged_only", "S3_neither"])]
    out = EV.evaluate({"design": design, "items": items}, {"r0": ["very_unusual"], "r1": ["usual"], "r2": ["usual"], "r3": ["usual"]})
    assert out["model_precision_perceived_unusual"] == 0.5
    assert isinstance(out["model_recall_perceived_unusual"], str) and "not estimable" in out["model_recall_perceived_unusual"]
    assert "NOT confirmed fraud" in out["label_meaning"]


def test_activation_enforces_the_predefined_acceptance_criteria():
    versions = sorted(p.name for p in (PV.REAL_DIR / "forecast").iterdir()) if (PV.REAL_DIR / "forecast").exists() else []
    if not versions:
        pytest.skip("no forecast version")
    before = PV.ACTIVE.read_text()
    with pytest.raises(RuntimeError, match="not activatable"):
        PV.activate("forecast", versions[-1], "must be refused: loses to the 3-month moving average")
    assert PV.ACTIVE.read_text() == before


def test_a_benchmark_can_never_be_activated():
    d = PV.REAL_DIR / "anomaly_ulb_benchmark"
    if not d.exists():
        pytest.skip("no benchmark")
    with pytest.raises(RuntimeError, match="not activatable"):
        PV.activate("anomaly_ulb_benchmark", sorted(p.name for p in d.iterdir())[-1], "must be refused")


def test_deactivate_and_rollback_restore_the_previous_state():
    before = PV.ACTIVE.read_text()
    v = PV.active()["credit_risk"]["version"]
    try:
        PV.deactivate("credit_risk", "test")
        registry.reload()
        with pytest.raises(registry.ModelUnavailable):
            registry.get("credit_risk")
        restored = PV.rollback("credit_risk", "test")
        registry.reload()
        assert restored["version"] == v and PV.active()["credit_risk"]["version"] == v
        assert registry.get("credit_risk") is not None
        actions = [h["action"] for h in PV.active()["_history"] if h["model"] == "credit_risk"]
        assert actions[-2:] == ["deactivate", "rollback"]
    finally:
        PV.ACTIVE.write_text(before)
        registry.reload()


def test_a_missing_model_is_reported_as_awaiting_not_as_an_error(client, monkeypatch):
    real_get = registry.get

    def no_anomaly(name):
        if name == "anomaly":
            raise registry.ModelUnavailable("'anomaly' is awaiting real-data training.")
        return real_get(name)
    monkeypatch.setattr(registry, "get", no_anomaly)
    a = client.post("/api/profiles/FINORA_USER_001/analyze").json()
    assert a["ml"]["anomaly"]["available"] is False and a["ml"]["anomaly"]["model_status"] == "awaiting_approved_model"
    assert "anomaly" not in a["ml_errors"]


def test_starting_the_app_never_trains(monkeypatch):
    import app.ml.train as T
    called = []
    monkeypatch.setattr(T, "main", lambda *a, **k: called.append(1))
    from app import main
    import inspect
    src = inspect.getsource(main)
    assert "train.run(" not in src and "train.main(" not in src and not called


# ---------------------------------------------------------------- every built model is usable (owner instruction 2026-11-15)
def test_experimental_activation_records_unmet_criteria_and_accepted_still_refuses(monkeypatch):
    before = PV.ACTIVE.read_text()
    try:
        v = sorted(p.name for p in (PV.REAL_DIR / "forecast").iterdir())[-1]
        with pytest.raises(RuntimeError, match="fails acceptance criteria"):
            PV.activate("forecast", v, "accepted must be refused")
        e = PV.activate("forecast", v, "experimental", experimental=True)
        assert e["status"] == "experimental" and e["unmet_criteria"] and "3-month moving average" in e["experimental_reason"]
        d = PV.REAL_DIR / "anomaly_ulb_benchmark"
        with pytest.raises(RuntimeError, match="benchmark"):
            PV.activate("anomaly_ulb_benchmark", sorted(p.name for p in d.iterdir())[-1], "never", experimental=True)
    finally:
        PV.ACTIVE.write_text(before)
        registry.reload()


def test_every_model_output_says_which_model_and_how_far_to_trust_it(client):
    a = client.post("/api/profiles/FINORA_USER_002/analyze").json()
    for name in ("credit_risk", "anomaly", "forecast", "peers"):
        info = a["ml"][name]["model_info"]
        e = PV.active()[name]
        assert info["version"] == e["version"] and info["status"] == e.get("status", "accepted")
    fc = a["ml"]["forecast"]
    if fc["model_info"]["status"] == "experimental":
        ev = fc["model_info"]["evaluation"]
        assert ev["xgboost_mae"] > ev["baseline_3m_average_mae"] and ev["beats_baseline"] is False   # disclosed, not hidden
        assert fc["available"] and fc["predicted_total_expense"] > 0 and fc["three_month_avg"] > 0     # real XGBoost output + baseline
    an = a["ml"]["anomaly"]
    d = an["score_distribution"]                                                                       # real Isolation Forest scores
    assert an["transactions_scored"] > 0 and d["scored"] == an["transactions_scored"] == sum(b["count"] for b in d["bins"])
    assert all(f["anomaly_score"] >= d["threshold"] - 1e-3 for f in an["flagged"])               # flags = above the model's threshold
    assert all(f["anomaly_score"] > 0 and f["reasons"] for f in an["flagged"])
    if an["model_info"]["status"] == "experimental":
        assert "NOT HUMAN-VALIDATED" in an["model_info"]["experimental_reason"]


def test_credit_risk_scoring_runs_the_real_model_with_shap():
    c = signed_in_client("credit")
    late = {"age": 30, "credit_limit": 100000, "months": [{"status": 2, "bill": 95000, "paid": 0}, {"status": 1, "bill": 90000, "paid": 2000},
                                                         {"status": 0, "bill": 80000, "paid": 5000}]}
    good = {"age": 30, "credit_limit": 100000, "months": [{"status": -1, "bill": 10000, "paid": 10000}] * 6}
    r1, r2 = c.post("/api/models/credit-risk/score", json=late).json(), c.post("/api/models/credit-risk/score", json=good).json()
    assert r1["default_probability_pct"] > r2["default_probability_pct"]                 # real inference, not a constant
    assert len(r1["factors"]) == 14 and r1["factors"][0]["shap"] > 0 and r1["factors"][0]["factor"] == "Latest payment status"
    assert "not a credit-bureau score" in r1["limitation"] and r1["model"]["test_roc_auc"] == 0.7831
    assert c.post("/api/models/credit-risk/score", json={**late, "months": late["months"][:2]}).status_code == 422
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).post("/api/models/credit-risk/score", json=late).status_code in (401, 403)


def test_a_suggestion_can_be_accepted_or_rejected_and_user_choices_are_never_overwritten():
    from .test_records import VALID, new_private, rec
    c = signed_in_client("sugg")
    pid = new_private(c, "Sugg")
    a = rec(c, pid, "transactions", {**VALID["transactions"], "description": "STARBUCKS STORE 01234"})
    b = rec(c, pid, "transactions", {**VALID["transactions"], "description": "SHELL OIL 57444"})
    u = rec(c, pid, "transactions", {**VALID["transactions"], "description": "STARBUCKS STORE 9", "category": "Groceries"})
    assert a["category_source"] == "model" and a["needs_review"]                          # a suggestion, awaiting confirmation
    ok = c.post(f"/api/profiles/{pid}/transactions/{a['id']}/suggestion", json={"action": "accept"}).json()
    assert ok["category"] == a["category"] and ok["category_source"] == "user" and not ok["needs_review"]
    no = c.post(f"/api/profiles/{pid}/transactions/{b['id']}/suggestion", json={"action": "reject"}).json()
    assert no["category"] is None and no["needs_review"] and no["suggested"] == b["category"]
    assert c.post(f"/api/profiles/{pid}/transactions/{u['id']}/suggestion", json={"action": "accept"}).status_code == 409   # user's own
    assert c.post(f"/api/profiles/{pid}/transactions/{a['id']}/suggestion", json={"action": "maybe"}).status_code == 422
    other = signed_in_client("sugg2")
    assert other.post(f"/api/profiles/{pid}/transactions/{b['id']}/suggestion", json={"action": "accept"}).status_code in (403, 404)
    # a description edit re-predicts suggestions but never a category the person chose or accepted
    p = c.patch(f"/api/profiles/{pid}/records/transactions/{a['id']}", json={"description": "SHELL OIL 1"}).json()
    assert p["category"] == ok["category"] and p["category_source"] == "user"


def test_categoriser_explains_its_suggestion_from_the_model_weights(client):
    r = client.post("/api/categorise", json={"texts": ["STARBUCKS STORE 01234", "ATM WDL SBI ATM DELHI"]}).json()
    assert r[0]["source"] == "model" and any("STARBUCKS" in w.upper() for w in r[0]["why"])
    assert r[1]["source"] == "rule" and "rule" in r[1]["why"][0]

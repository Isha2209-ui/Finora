"""Model quality gates for the ACTIVE real-data models (Phase 6). A model that falls below its documented bar fails the build.
Gates check the recorded evaluation; the evaluations themselves are produced by python -m app.ml.train on real data."""
import pytest

from app.ml import categoriser, provenance as PV, registry


@pytest.fixture(scope="module")
def m():
    return registry.metrics()


def _version_metrics(name):
    """Metrics of the ACTIVE version, or (when the model is not active) of its latest trained version, so the gates always run."""
    act = PV.active().get(name)
    folder = (PV.REAL_DIR / name / act["version"]) if act else sorted((PV.REAL_DIR / name).glob("*/metrics.json"))[-1].parent
    return PV.load_metrics(folder)


def _active(name):
    assert (PV.REAL_DIR / name).exists(), f"{name}: never trained on real data"


def test_credit_risk_quality(m):
    _active("credit_risk")
    c = m["credit_risk"]
    x, lr, rule = c["test"]["xgboost"], c["test"]["logistic_regression_baseline"], c["test"]["rule_baseline_delayed_last_month"]
    assert c["split"]["train"] + c["split"]["validation"] + c["split"]["test"] == 30000      # the real UCI dataset, 70/15/15
    assert x["roc_auc"] >= 0.75                                                                # published results are ~0.77-0.78
    assert abs(x["roc_auc"] - c["cross_validation"]["xgboost_roc_auc_mean"]) < 0.03           # test agrees with 5-fold CV
    assert x["roc_auc"] > lr["roc_auc"] and x["roc_auc"] > rule["roc_auc"]
    notes = m["_provenance"]["credit_risk"]["datasets"][0]["data_notes"]
    assert notes["duplicate_rows_excluding_id"] == 35 and notes["negative_bill_amount_rows"] > 0


def test_categoriser_quality(m):
    _active("categoriser")
    c = m["categoriser"]
    h = c["held_out_merchants_oklahoma"]
    assert h["macro_f1"] > h["keyword_rule_macro_f1"]              # pre-registered pass criterion
    assert "not validated on Indian" in m["_provenance"]["categoriser"]["deployment_label"]
    assert c["independent_test_dc"]["rows"] > 0 and c["independent_test_moneyvis_uk_personal"]["rows"] > 0


def test_anomaly_is_reported_without_an_accuracy_claim():
    _active("anomaly")
    a = _version_metrics("anomaly")
    assert a["accuracy"].startswith("NOT MEASURED")
    assert a["human_review"]["what_is_labelled"].startswith("perceived unusualness")
    assert min(a["flag_stability_jaccard_vs_seeds"].values()) >= 0.7
    assert "log_amount" not in a["features"] and "source_rarity" not in a["features"]
    assert a["human_review"]["items"] == 300 and set(a["human_review"]["design"]) == {"S1_model_flagged", "S2_rule_flagged_only", "S3_neither"}
    reviewed_ok = bool((a["human_review"].get("result") or {}).get("model_precision_perceived_unusual", 0) >= 0.5)
    assert (PV.status_of("anomaly") == "accepted") == reviewed_ok           # accepted only after a supportive human review
    if PV.status_of("anomaly") == "experimental":
        assert PV.active()["anomaly"]["unmet_criteria"] and "NOT HUMAN-VALIDATED" in PV.active()["anomaly"]["experimental_reason"]


def test_forecast_is_evaluated_chronologically_and_reported_as_is():
    _active("forecast")
    f = _version_metrics("forecast")
    e = f["evaluation"]
    assert "chronological" in e["method"].lower() and e["test_months"] >= 36
    assert e["beats_moving_average_on_mae"] == (e["xgboost"]["mae"] < e["baseline_moving_average_3m"]["mae"])
    assert (PV.status_of("forecast") == "accepted") == e["beats_moving_average_on_mae"]   # accepted only if it beats the baseline
    if PV.status_of("forecast") == "experimental":
        assert PV.active()["forecast"]["unmet_criteria"]


def test_peers_clustering_is_stable_across_implicates(m):
    _active("peers")
    p = m["peers"]
    assert 2 <= p["chosen_k"] <= 8
    assert p["stability"]["cross_implicate_ari_min"] >= 0.7
    assert abs(sum(g["weighted_share_pct"] for g in p["groups"]) - 100) < 0.5


@pytest.mark.parametrize("text,expected", [
    ("NACH/DR/BAJAJ FINANCE EMI/88213344", "EMI"),
    ("ATM WDL HDFC ATM JAIPUR", "Cash"),
    ("ACH D- BSE LTD-PARAG PARIKH FLEXI", "Investment"),
])
def test_bank_side_examples_are_decided_by_rules(text, expected):
    r = categoriser.safe_predict([text])[0]
    assert r["category"] == expected and r["source"] == "rule"


def test_merchant_predictions_come_from_the_model_or_are_left_for_review():
    for r in categoriser.safe_predict(["STARBUCKS STORE 01234", "SHELL OIL 57444"]):
        assert r["source"] in ("model", "none")
        assert r["category"] is not None or r["needs_review"]


def test_predictions_are_deterministic(client):
    a = client.post("/api/profiles/FINORA_USER_002/analyze").json()
    b = client.post("/api/profiles/FINORA_USER_002/analyze").json()
    assert a["ml"]["forecast"] == b["ml"]["forecast"]
    assert a["ml"]["credit_risk"]["overall_default_probability_pct"] == b["ml"]["credit_risk"]["overall_default_probability_pct"]
    assert a["fire"]["success_probability_pct"] == b["fire"]["success_probability_pct"]

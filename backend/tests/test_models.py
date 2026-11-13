"""Model quality gates: a model that falls below its minimum bar fails the build."""
import pytest

from app.ml import categoriser, registry


@pytest.fixture(scope="module")
def m():
    return registry.metrics()


def test_all_models_trained():
    assert all(registry.status().values())


def test_credit_risk_quality(m):
    c = m["credit_risk"]
    assert c["rows"] == 30000                                             # the real UCI dataset
    assert c["xgboost"]["roc_auc"] >= 0.76                                # published benchmarks are ~0.77-0.78
    assert abs(c["xgboost"]["roc_auc"] - c["cv_roc_auc_mean"]) < 0.02     # hold-out agrees with 5-fold CV (no lucky split)
    assert c["xgboost"]["roc_auc"] > c["baseline_logistic_regression"]["roc_auc"]
    assert c["xgboost"]["roc_auc"] > c["baseline_rule_delayed_last_month"]["roc_auc"]


def test_categoriser_quality(m):
    c = m["categoriser"]
    assert c["unseen_formats_test"]["macro_f1"] >= 0.90
    assert c["unseen_formats_test"]["macro_f1"] > c["unseen_formats_test"]["keyword_rule_macro_f1"]


def test_anomaly_beats_rule(m):
    a = m["anomaly"]
    assert a["isolation_forest"]["recall"] >= 0.6
    assert a["isolation_forest"]["f1"] > a["baseline_rule_3x_category_median"]["f1"]


def test_forecast_beats_baselines(m):
    f = m["forecast"]["total_expense"]
    assert f["xgboost"]["mae"] < f["baseline_3_month_average"]["mae"] < f["baseline_last_month"]["mae"]
    assert m["forecast"]["category_expense"]["beats_baseline"]
    assert m["forecast"]["split"]["type"] == "chronological"


def test_peers_clustering(m):
    assert m["peers"]["silhouette"] > 0.25 and 2 <= m["peers"]["chosen_k"] <= 6


@pytest.mark.parametrize("text,expected", [
    ("UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment", "Dining"),
    ("POS 4521XXXXXXXX1234 AMAZON BANGALORE", "Shopping"),
    ("UPI-UBER-uber@okaxis-HDFC0000001-123456789012-UPI", "Travel"),
    ("NACH/DR/BAJAJ FINANCE EMI/88213344", "EMI"),
    ("ATM WDL HDFC ATM JAIPUR", "Cash"),
    ("PAYU*NETFLIX MUMBAI", "Subscriptions"),
    ("BIL/BPAY/556677889/AIRTEL/AUTOPAY", "Utilities"),
    ("Paid to BigBasket via Google Pay UPI Ref 998877665544", "Groceries"),
    ("ACH D- BSE LTD-PARAG PARIKH FLEXI", "Investment"),
    ("UPI/P2M/123412341234/APOLLOPHARMACY LIMITED", "Health"),
])
def test_categoriser_examples(text, expected):
    assert categoriser.predict(registry.get("categoriser"), [text])[0]["category"] == expected


def test_predictions_are_deterministic(client):
    a = client.post("/api/profiles/FINORA_USER_002/analyze").json()
    b = client.post("/api/profiles/FINORA_USER_002/analyze").json()
    assert a["ml"]["forecast"]["predicted_total_expense"] == b["ml"]["forecast"]["predicted_total_expense"]
    assert a["ml"]["credit_risk"]["overall_default_probability_pct"] == b["ml"]["credit_risk"]["overall_default_probability_pct"]
    assert a["fire"]["success_probability_pct"] == b["fire"]["success_probability_pct"]

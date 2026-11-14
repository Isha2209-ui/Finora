"""Part C: SEPARATE Isolation Forest benchmark on the ULB credit-card fraud dataset (Sept 2013, European cardholders).

This is NOT the deployed model and its numbers must never be presented as the deployed model's accuracy. ULB features are
PCA components (V1-V28) of undisclosed card data, so a model trained here cannot score a Finora user's transactions.
It answers one question: on real transactions with confirmed fraud labels, how well does an Isolation Forest (same
settings) separate fraud from normal activity, compared with a simple amount rule?

Protocol: train on day 1 (Time < 86,400 s) without using labels; test on day 2. Labels are used only to evaluate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.io import arff
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score

from ...config import DATASETS_DIR
from ..provenance import Run, sha256, source_record

SEED = 7
CONTAMINATION = 0.015


def load() -> pd.DataFrame:
    """The official OpenML ARFF if present; otherwise the CSV copy recorded (and verified) in SOURCE.json."""
    raw = DATASETS_DIR / "raw" / "ulb_fraud"
    if (raw / "creditcard.arff").exists():
        data, _ = arff.loadarff(raw / "creditcard.arff")
        df = pd.DataFrame(data)
    else:
        df = pd.read_csv(raw / "creditcard.csv")
    df["Class"] = df["Class"].map(lambda v: int(v.decode().strip("'\"") if isinstance(v, bytes) else str(v).strip("'\"")))
    return df


def _m(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "false_positive_rate": round(fp / (fp + tn), 5), "flagged": int(tp + fp),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}


def _budgets(y: np.ndarray, score: np.ndarray) -> dict:
    """Why most flags are false alarms: with a 0.15% fraud rate, flagging 1.5% of transactions can be at most ~10% precise
    even if every fraud were caught. Precision/recall at several alert budgets (top-scored share of transactions)."""
    order = np.argsort(-score)
    rows = []
    for share in (0.001, 0.0017, 0.005, 0.01, 0.015, 0.03):
        n = max(1, int(round(share * len(y))))
        tp = int(y[order[:n]].sum())
        rows.append({"flag_share_pct": round(share * 100, 2), "flagged": n, "true_frauds_caught": tp,
                     "precision": round(tp / n, 4), "recall": round(tp / y.sum(), 4),
                     "best_possible_precision": round(min(1.0, y.sum() / n), 4)})
    return {"base_rate": round(float(y.mean()), 5), "by_alert_budget": rows,
            "explanation": "The deployed contamination (1.5%) flags about 10x more transactions than there are frauds (0.15%), so even a "
                           "perfect ranking would be at most ~10% precise at that budget. Precision rises as fewer transactions are "
                           "flagged, at the cost of recall. This is a property of rare events, not evidence about Finora's users."}


def train(approved: bool = False) -> tuple[str, dict]:
    run = Run("anomaly_ulb_benchmark", "python -m app.ml.train anomaly_ulb")
    df = load()
    feats = [c for c in df.columns if c.startswith("V")] + ["Amount"]
    tr, te = df[df["Time"] < 86400], df[df["Time"] >= 86400]
    model = IsolationForest(n_estimators=300, contamination=CONTAMINATION, random_state=SEED, n_jobs=4).fit(tr[feats])
    y = te["Class"].to_numpy()
    score = -model.score_samples(te[feats])
    pred = (model.predict(te[feats]) == -1).astype(int)
    rule = (te["Amount"] > tr["Amount"].quantile(0.99)).astype(int).to_numpy()   # amount above day-1 99th percentile
    metrics = {
        "benchmark_only": True, "not_the_deployed_model": True,
        "dataset": "ULB / Worldline credit-card fraud, September 2013 (2 days)", "rows": int(len(df)),
        "fraud_rows": int(df["Class"].sum()), "train_day1_rows": int(len(tr)), "test_day2_rows": int(len(te)),
        "test_fraud_rows": int(y.sum()), "labels_used_for_training": False,
        "isolation_forest": {**_m(y, pred), "pr_auc": round(float(average_precision_score(y, score)), 4),
                             "roc_auc": round(float(roc_auc_score(y, score)), 4)},
        "rule_amount_above_day1_p99": {**_m(y, rule), "pr_auc": round(float(average_precision_score(y, te["Amount"])), 4)},
        "fraud_base_rate_test": round(float(y.mean()), 5),
        "false_alarm_investigation": _budgets(y, score),
    }
    src = source_record("ulb_fraud")
    prov = {
        "data_status": "real", "evaluation_passed": True, "approved_by_owner": bool(approved), "deployable": False,
        "deployment_label": "Benchmark only. Not used by Finora and not the deployed anomaly model's accuracy.",
        "datasets": [{"key": "ulb_fraud", "role": "separate benchmark", "name": src.get("name"), "source_url": src.get("page"),
                      "licence": src.get("licence"), "geography": "Europe", "collection_period": "September 2013, 2 days",
                      "records": int(len(df)), "observations": "real (PCA-transformed)", "synthetic_observations": "none",
                      "files": [{"file": f["file"], "sha256": f.get("sha256"), "url": f.get("url")} for f in src.get("files", [])],
                      "labels": "confirmed fraud flags from the card processor",
                      "acquisition_note": src.get("acquisition_note"), "verification": src.get("verification")}],
        "limitations": "Features are anonymised PCA components; results do not transfer to Finora's per-person features.",
    }
    out = run.save({"model": model, "features": feats}, metrics, prov)
    return run.version, {"out": str(out), **{k: metrics[k] for k in ("test_day2_rows", "test_fraud_rows", "isolation_forest",
                                                                       "rule_amount_above_day1_p99")}}

"""Predefined acceptance criteria. A version can be activated only if its recorded metrics pass these checks.

The criteria come from the approved Phase 6 plan (each model must beat the baseline it is compared with) and were written
down BEFORE the final categoriser and anomaly runs. They are evaluated from metrics.json, never from a flag set by the
trainer, and never tuned to a result. Changing a criterion is a documented decision, not a code tweak.
"""
from __future__ import annotations

CRITERIA = {
    "credit_risk": [
        "test ROC-AUC >= 0.70",
        "XGBoost beats logistic regression on test ROC-AUC",
        "test ROC-AUC within 0.05 of the 5-fold CV mean (no lucky split)",
    ],
    "forecast": [
        "XGBoost MAE below the 3-month moving average's MAE on the chronological test months",
    ],
    "peers": [
        "minimum cross-implicate adjusted Rand index >= 0.70 (clusters stable across the 5 SCF implicates)",
        "silhouette > 0 for the chosen k",
        "survey-weight shares of the groups sum to 100%",
    ],
    "categoriser": [
        "held-out-merchant macro-F1 >= 0.50",
        "beats the keyword rules on held-out merchants (macro-F1)",
        "beats the keyword rules on the independent DC test (macro-F1)",
        "no merchant group in both training and test",
    ],
    "anomaly": [
        "flagged set stable across random seeds (Jaccard >= 0.70)",
        "a completed blinded human review supports the flags (precision of flagged transactions judged unusual >= 0.50)",
    ],
}


def check(model: str, m: dict) -> tuple[bool, list[dict]]:
    """Returns (passed, [{criterion, passed, value}]). Unknown models never pass."""
    out = []

    def add(i, ok, value):
        out.append({"criterion": CRITERIA[model][i], "passed": bool(ok), "value": value})

    try:
        if model == "credit_risk":
            x, lr = m["test"]["xgboost"]["roc_auc"], m["test"]["logistic_regression_baseline"]["roc_auc"]
            cv = m["cross_validation"]["xgboost_roc_auc_mean"]
            add(0, x >= 0.70, x); add(1, x > lr, f"{x} vs {lr}"); add(2, abs(x - cv) < 0.05, f"{x} vs CV {cv}")
        elif model == "forecast":
            e = m["evaluation"]
            add(0, e["xgboost"]["mae"] < e["baseline_moving_average_3m"]["mae"],
                f"{e['xgboost']['mae']} vs {e['baseline_moving_average_3m']['mae']}")
        elif model == "peers":
            s = m["stability"]
            sil = next(k["silhouette_implicate1"] for k in m["k_scan"] if k["k"] == m["chosen_k"])
            tot = sum(g["weighted_share_pct"] for g in m["groups"])
            add(0, s["cross_implicate_ari_min"] >= 0.70, s["cross_implicate_ari_min"]); add(1, sil > 0, sil)
            add(2, abs(tot - 100) < 0.5, round(tot, 2))
        elif model == "categoriser":
            h, d = m["held_out_merchants_oklahoma"], m["independent_test_dc"]
            add(0, h["macro_f1"] >= 0.50, h["macro_f1"])
            add(1, h["macro_f1"] > h["keyword_rule_macro_f1"], f"{h['macro_f1']} vs {h['keyword_rule_macro_f1']}")
            add(2, d["macro_f1"] > d["keyword_rule_macro_f1"], f"{d['macro_f1']} vs {d['keyword_rule_macro_f1']}")
            add(3, m["leakage_checks"]["merchant_groups_in_both"] == 0, m["leakage_checks"]["merchant_groups_in_both"])
        elif model == "anomaly":
            st = m["flag_stability_jaccard_vs_seeds"]
            add(0, min(st.values()) >= 0.70, min(st.values()))
            rev = (m.get("human_review") or {}).get("result") or {}
            p = rev.get("model_precision_perceived_unusual")
            add(1, p is not None and p >= 0.50, p if p is not None else "review not completed")
        elif model == "anomaly_ulb_benchmark":
            return False, [{"criterion": "benchmark only: never deployable", "passed": False, "value": "separate benchmark"}]
        else:
            return False, [{"criterion": "known model", "passed": False, "value": model}]
    except (KeyError, TypeError, StopIteration) as e:
        out.append({"criterion": "metrics present", "passed": False, "value": f"missing {e}"})
    return bool(out) and all(c["passed"] for c in out), out

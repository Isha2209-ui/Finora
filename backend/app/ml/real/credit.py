"""Credit risk on the verified UCI dataset: XGBoost + SHAP (architecture unchanged), 70/15/15 split, 5-fold CV,
logistic-regression and rule baselines. Feature engineering is the existing credit_risk.features_from_history."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .. import credit_risk as CR
from ..provenance import Run, sha256, source_record

SEED = 7
VERIFICATION = ("The local CSV is a cell-for-cell copy of the official UCI .xls: 30,000 x 25 values, 750,000 of 750,000 cells "
                "identical, 0 rows differing (checked 2026-11-15 with xlrd 2.0.2 in a scratch environment against "
                "'default of credit card clients.xls', SHA-256 30c6be3abd8dcfd3e6096c828bad8c2f011238620f5369220bd60cfc82700933, "
                "from the official zip).")


def data_notes(raw: pd.DataFrame) -> dict:
    return {"rows": int(len(raw)), "columns": int(raw.shape[1]), "missing_values": int(raw.isna().sum().sum()),
            "duplicate_rows_excluding_id": int(raw.drop(columns="ID").duplicated().sum()),
            "duplicate_treatment": "Kept: identical feature values for different customer IDs are plausible (distinct customers); "
                                   "they are counted and disclosed, not removed.",
            "negative_bill_amount_rows": int((raw[CR.BILL_COLS] < 0).any(axis=1).sum()),
            "negative_bill_treatment": "Kept: a negative bill is a credit balance (overpayment). Utilisation uses max(0, bill).",
            "undocumented_codes": {"EDUCATION": sorted(int(x) for x in set(raw["EDUCATION"]) - {1, 2, 3, 4}),
                                   "MARRIAGE": sorted(int(x) for x in set(raw["MARRIAGE"]) - {1, 2, 3})},
            "undocumented_code_treatment": "No effect: SEX, EDUCATION and MARRIAGE are excluded from the model (fairness and "
                                           "portability), so their undocumented codes are not used.",
            "pay_status_codes": "-2 no consumption, -1 paid in full, 0 revolving credit, 1..8 months of payment delay (codes -2 and 0 "
                                "are not in the original paper's description; they are kept as observed).",
            "target_positive": int(raw[CR.TARGET].sum()), "target_negative": int((1 - raw[CR.TARGET]).sum())}


def train(approved: bool) -> tuple[str, dict]:
    run = Run("credit_risk", "python -m app.ml.train credit_risk")
    raw = pd.read_csv(CR.DATASET)
    X, y = CR.load_dataset()
    X_tmp, X_te, y_tmp, y_te = train_test_split(X, y, test_size=0.15, stratify=y, random_state=SEED)
    X_tr, X_va, y_tr, y_va = train_test_split(X_tmp, y_tmp, test_size=0.15 / 0.85, stratify=y_tmp, random_state=SEED)
    cv = cross_val_score(CR._xgb(SEED), X_tr, y_tr, scoring="roc_auc", cv=StratifiedKFold(5, shuffle=True, random_state=SEED))
    model = CR._xgb(SEED).fit(X_tr, y_tr)
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)).fit(X_tr, y_tr)
    cv_lr = cross_val_score(make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)), X_tr, y_tr, scoring="roc_auc",
                            cv=StratifiedKFold(5, shuffle=True, random_state=SEED))
    # decision threshold chosen on the VALIDATION set only (max F1); the test set is touched once, below
    pv = model.predict_proba(X_va)[:, 1]
    grid = np.linspace(0.05, 0.8, 76)
    thr = float(grid[np.argmax([f1_score(y_va, pv >= t) for t in grid])])
    thr_lr = float(grid[np.argmax([f1_score(y_va, lr.predict_proba(X_va)[:, 1] >= t) for t in grid])])

    def evaluate(p, t):
        pred = (p >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_te, pred).ravel()
        return {"roc_auc": round(float(roc_auc_score(y_te, p)), 4), "pr_auc": round(float(average_precision_score(y_te, p)), 4),
                "brier": round(float(brier_score_loss(y_te, p)), 4), "threshold": round(t, 3),
                "precision": round(float(precision_score(y_te, pred)), 4), "recall": round(float(recall_score(y_te, pred)), 4),
                "f1": round(float(f1_score(y_te, pred)), 4), "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}

    p_te = model.predict_proba(X_te)[:, 1]
    rule = (X_te["pay_status_latest"] >= 1).astype(int)
    xgb_m, lr_m = evaluate(p_te, thr), evaluate(lr.predict_proba(X_te)[:, 1], thr_lr)
    rule_m = evaluate(rule.to_numpy().astype(float), 0.5)
    import shap
    sv = shap.TreeExplainer(model).shap_values(X_te)
    shap_global = sorted(zip(CR.FEATURES, np.abs(sv).mean(axis=0).tolist()), key=lambda kv: -kv[1])
    metrics = {
        "task": "Probability that a card holder misses next month's payment (default payment next month)",
        "split": {"method": "stratified 70/15/15 train/validation/test, random_state=7", "train": int(len(X_tr)),
                  "validation": int(len(X_va)), "test": int(len(X_te))},
        "cross_validation": {"method": "5-fold stratified CV on the training part only", "xgboost_roc_auc_mean": round(float(cv.mean()), 4),
                             "xgboost_roc_auc_std": round(float(cv.std()), 4), "logistic_regression_roc_auc_mean": round(float(cv_lr.mean()), 4),
                             "logistic_regression_roc_auc_std": round(float(cv_lr.std()), 4)},
        "test": {"xgboost": xgb_m, "logistic_regression_baseline": lr_m, "rule_baseline_delayed_last_month": rule_m},
        "beats_logistic_regression_on_test_roc_auc": xgb_m["roc_auc"] > lr_m["roc_auc"],
        "shap_global_mean_abs": [{"feature": CR.FEATURE_LABELS[f], "mean_abs_shap": round(v, 4)} for f, v in shap_global],
        "features": [CR.FEATURE_LABELS[f] for f in CR.FEATURES],
    }
    passed = xgb_m["roc_auc"] >= 0.70 and abs(xgb_m["roc_auc"] - float(cv.mean())) < 0.05
    src = source_record("uci_credit")
    prov = {
        "data_status": "real", "evaluation_passed": bool(passed), "approved_by_owner": bool(approved),
        "deployment_label": "Trained on real Taiwanese card data (2005); not an Indian credit-bureau score",
        "datasets": [{
            "key": "uci_credit", "name": "Default of Credit Card Clients", "publisher": "UCI Machine Learning Repository (I-Cheng Yeh, Che-hui Lien)",
            "source_url": "https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients", "doi": "10.24432/C55S3H",
            "download_url": "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip",
            "publication": "Yeh & Lien (2009), Expert Systems with Applications 36(2) 2473-2480",
            "collection_period": "April-September 2005 (target: October 2005)", "geography": "Taiwan",
            "population": "Credit-card clients of a Taiwanese bank", "records": 30000, "features": 23,
            "format": "Excel .xls (official); CSV copy used for training", "target": "default payment next month (1 = default)",
            "observations": "real, anonymised", "synthetic_observations": "none", "licence": "CC BY 4.0",
            "file_used": str(CR.DATASET.name), "file_sha256": sha256(CR.DATASET), "official_zip_sha256": (src.get("files") or [{}])[0].get("sha256"),
            "downloaded": src.get("downloaded_at"), "verification": VERIFICATION, "data_notes": data_notes(raw),
            "preprocessing": "Per customer: 14 behavioural features from 6 months of status, bills and payments (credit_risk."
                             "features_from_history): money as ratios to the credit limit, delay counts, utilisation and repayment "
                             "ratios. SEX, EDUCATION and MARRIAGE excluded.",
            "missing_values": "none in the source", "duplicates": "35 duplicate feature rows kept and disclosed",
            "known_biases": "Taiwan 2005, one bank, card customers only; 22% default rate; not representative of Indian borrowers."}],
        "methodology": "XGBoost classifier (unchanged hyperparameters) + SHAP TreeExplainer; threshold maximising F1 on validation.",
        "limitations": "Learned on Taiwanese card customers in 2005. It estimates a default-risk pattern from payment behaviour; it is "
                       "not an Indian credit-bureau score and its accuracy for Indian borrowers is not established.",
        "reproducible": "python -m app.ml.train credit_risk (seed 7) with the same CSV (SHA-256 above)",
    }
    out = run.save({"model": model, "threshold": thr, "base_rate": float(y.mean()), "features": CR.FEATURES}, metrics, prov)
    return run.version, {"out": str(out), "passed": passed, "test": xgb_m, "lr": lr_m, "cv": metrics["cross_validation"]}

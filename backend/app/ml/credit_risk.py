"""Credit-risk model - probability of missing a card payment next month.

Trained on REAL data: UCI "Default of Credit Card Clients" (30,000 customers of a
Taiwanese bank, 2005; Yeh & Lien 2009). The model learns behavioural PATTERNS of
default (payment delays, utilisation, repayment ratio) - it is not an Indian credit score.

To keep the model portable to Finora users, every money feature is a RATIO to the
credit limit, and demographic columns (sex, education, marriage) are deliberately
dropped - both for fairness and because they are not needed.

Evaluation: stratified 80/20 hold-out + 5-fold cross-validation, ROC-AUC, PR-AUC,
compared against (a) logistic regression and (b) a one-line rule "delayed last month".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ..config import DATASETS_DIR

DATASET = DATASETS_DIR / "uci_credit_card_default.csv"
PAY_COLS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]  # most recent first
BILL_COLS = [f"BILL_AMT{i}" for i in range(1, 7)]
PAID_COLS = [f"PAY_AMT{i}" for i in range(1, 7)]
TARGET = "default.payment.next.month"

FEATURES = ["age", "pay_status_latest", "pay_status_2", "pay_status_3", "max_delay_6m", "months_delayed_6m",
            "months_revolving_6m", "months_paid_full_6m", "utilisation_latest", "utilisation_avg_6m",
            "utilisation_trend", "repayment_ratio_latest", "repayment_ratio_avg", "months_zero_payment"]
FEATURE_LABELS = {
    "age": "Age", "pay_status_latest": "Latest payment status", "pay_status_2": "Payment status 2 months ago",
    "pay_status_3": "Payment status 3 months ago", "max_delay_6m": "Worst payment delay (6 months)",
    "months_delayed_6m": "Months with a delayed payment", "months_revolving_6m": "Months paying only part of the bill",
    "months_paid_full_6m": "Months paid in full", "utilisation_latest": "Latest credit utilisation",
    "utilisation_avg_6m": "Average utilisation (6 months)", "utilisation_trend": "Utilisation trend",
    "repayment_ratio_latest": "Share of last bill repaid", "repayment_ratio_avg": "Average share of bill repaid",
    "months_zero_payment": "Months with no payment made",
}


def features_from_history(age: float, limit: float, status: list[int], bills: list[float], paid: list[float]) -> dict:
    """status/bills/paid are most-recent-first lists of 6 months."""
    status = (list(status) + [status[-1] if len(status) else 0] * 6)[:6]
    bills, paid = (list(bills) + [0] * 6)[:6], (list(paid) + [0] * 6)[:6]
    limit = max(float(limit), 1.0)
    util = [max(0.0, b) / limit for b in bills]
    # paid[i] settles bill[i+1] (the previous statement)
    ratios = [min(2.0, paid[i] / bills[i + 1]) if bills[i + 1] > 0 else 1.0 for i in range(5)]
    return {
        "age": age, "pay_status_latest": status[0], "pay_status_2": status[1], "pay_status_3": status[2],
        "max_delay_6m": max(status), "months_delayed_6m": sum(s > 0 for s in status),
        "months_revolving_6m": sum(s == 0 for s in status), "months_paid_full_6m": sum(s < 0 for s in status),
        "utilisation_latest": util[0], "utilisation_avg_6m": float(np.mean(util)),
        "utilisation_trend": util[0] - float(np.mean(util[3:])),
        "repayment_ratio_latest": ratios[0], "repayment_ratio_avg": float(np.mean(ratios)),
        "months_zero_payment": sum(p <= 0 for p in paid),
    }


def load_dataset() -> tuple[pd.DataFrame, pd.Series]:
    raw = pd.read_csv(DATASET)
    rows = [features_from_history(r.AGE, r.LIMIT_BAL, [getattr(r, c) for c in PAY_COLS],
                                  [getattr(r, c) for c in BILL_COLS], [getattr(r, c) for c in PAID_COLS])
            for r in raw.itertuples(index=False)]
    return pd.DataFrame(rows)[FEATURES], raw[TARGET].astype(int)


def _xgb(seed):
    return XGBClassifier(n_estimators=350, max_depth=4, learning_rate=0.04, subsample=0.85, colsample_bytree=0.85,
                         min_child_weight=5, reg_lambda=2.0, eval_metric="logloss", random_state=seed, n_jobs=4)


def train(seed: int = 7) -> tuple[dict, dict]:
    X, y = load_dataset()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)
    model = _xgb(seed).fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]
    logit = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(Xtr, ytr)
    p_lr = logit.predict_proba(Xte)[:, 1]
    rule = (Xte["pay_status_latest"] >= 1).astype(int)

    cv = cross_val_score(_xgb(seed), X, y, scoring="roc_auc", cv=StratifiedKFold(5, shuffle=True, random_state=seed))
    # threshold that maximises F1 on the TRAINING folds (never on the test set)
    ptr = model.predict_proba(Xtr)[:, 1]
    grid = np.linspace(0.1, 0.7, 61)
    thr = float(grid[np.argmax([f1_score(ytr, ptr >= t) for t in grid])])
    pred = (p >= thr).astype(int)
    fpr, tpr, _ = roc_curve(yte, p)
    idx = np.linspace(0, len(fpr) - 1, 60).astype(int)
    tn, fp, fn, tp = confusion_matrix(yte, pred).ravel()

    def cls(pred_):
        return {"precision": round(float(precision_score(yte, pred_)), 3), "recall": round(float(recall_score(yte, pred_)), 3),
                "f1": round(float(f1_score(yte, pred_)), 3)}

    imp = sorted(zip(FEATURES, model.feature_importances_.tolist()), key=lambda kv: -kv[1])
    metrics = {
        "model": "XGBClassifier", "dataset": "UCI Default of Credit Card Clients (Yeh & Lien, 2009) - 30,000 real customers",
        "rows": int(len(X)), "train_rows": int(len(Xtr)), "test_rows": int(len(Xte)), "default_rate_pct": round(float(y.mean() * 100), 2),
        "features": len(FEATURES), "threshold": round(thr, 3),
        "xgboost": {"roc_auc": round(float(roc_auc_score(yte, p)), 4), "pr_auc": round(float(average_precision_score(yte, p)), 4),
                    "brier": round(float(brier_score_loss(yte, p)), 4), **cls(pred)},
        "cv_roc_auc_mean": round(float(cv.mean()), 4), "cv_roc_auc_std": round(float(cv.std()), 4),
        "baseline_logistic_regression": {"roc_auc": round(float(roc_auc_score(yte, p_lr)), 4),
                                         "pr_auc": round(float(average_precision_score(yte, p_lr)), 4)},
        "baseline_rule_delayed_last_month": {"roc_auc": round(float(roc_auc_score(yte, rule)), 4), **cls(rule)},
        "beats_logistic_regression": bool(roc_auc_score(yte, p) > roc_auc_score(yte, p_lr)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "roc_curve": [{"fpr": round(float(fpr[i]), 4), "tpr": round(float(tpr[i]), 4)} for i in idx],
        "feature_importance": [{"feature": FEATURE_LABELS[f], "importance": round(v, 4)} for f, v in imp],
        "limitations": "Trained on 2005 Taiwanese card data: it captures general default patterns, not Indian bureau scores. "
                       "Demographic columns were excluded on purpose.",
    }
    return {"model": model, "threshold": thr, "base_rate": float(y.mean())}, metrics


def _band(p: float) -> str:
    return "low" if p < 0.15 else "moderate" if p < 0.30 else "high" if p < 0.50 else "very high"


def analyse(art: dict, ident) -> dict:
    """Score each of the person's cards + an overall figure, with SHAP explanations."""
    import shap

    if not ident.cards:
        return {"has_cards": False, "note": "No credit cards on file, so card-default risk is not applicable."}
    st = pd.DataFrame(ident.card_statements)
    rows, meta = [], []
    for c in ident.cards:
        s = st[st["card_id"] == c["id"]].sort_values("month", ascending=False).head(6)
        if len(s) < 3:
            continue
        rows.append(features_from_history(ident.user["age"], c["credit_limit"], s["payment_status"].tolist(),
                                          s["bill_amount"].tolist(), s["paid_amount"].tolist()))
        meta.append(c)
    if not rows:
        return {"has_cards": True, "note": "Not enough statement history (need 3+ months)."}
    X = pd.DataFrame(rows)[FEATURES]
    proba = art["model"].predict_proba(X)[:, 1]
    sv = shap.TreeExplainer(art["model"]).shap_values(X)
    cards = []
    for i, c in enumerate(meta):
        contrib = sorted(zip(FEATURES, sv[i].tolist(), X.iloc[i].tolist()), key=lambda t: -abs(t[1]))[:5]
        cards.append({
            "card": f"{c['issuer']} {c['card_name']}", "last4": c["last4"],
            "default_probability_pct": round(float(proba[i]) * 100, 1), "risk_band": _band(float(proba[i])),
            "top_factors": [{"factor": FEATURE_LABELS[f], "value": round(float(v), 3),
                             "effect": "raises risk" if s > 0 else "lowers risk", "shap": round(float(s), 3)}
                            for f, s, v in contrib],
        })
    worst = max(cards, key=lambda c: c["default_probability_pct"])
    return {
        "has_cards": True, "cards": cards,
        "overall_default_probability_pct": worst["default_probability_pct"], "overall_risk_band": worst["risk_band"],
        "driven_by_card": worst["card"],
        "population_base_rate_pct": round(art["base_rate"] * 100, 1),
        "interpretation": "Probability of missing next month's minimum payment, estimated from payment behaviour "
                          "patterns learned on real card data. It is a risk signal, not a credit-bureau score.",
    }


def score_features(art: dict, feats: dict) -> float:
    return float(art["model"].predict_proba(pd.DataFrame([feats])[FEATURES])[:, 1][0])

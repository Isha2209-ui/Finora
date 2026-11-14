"""Anomaly Detector (Isolation Forest) - finds transactions that are unusual FOR THIS PERSON,
looking across all of their bank accounts and credit cards together.

Features are relative to the person's own history, so Rs 5,000 can be normal for one
user and unusual for another:
  ratio_to_cat_median   amount / the user's median for that category
  robust_z              (amount - median) / IQR within the user's category
  share_of_month_cat    share of that month's category spend taken by this one transaction
  ratio_to_user_p95     amount / the user's 95th-percentile transaction (any category)
  source_rarity         1 - share of the user's transactions made from this account/card
  same_day_same_cat     number of same-category transactions that day (repeat activity)
  log_amount            scale

`injected_anomaly_label` is used ONLY to evaluate the model afterwards. It is never a feature.
Unusual does NOT mean fraudulent, and anomaly scores are not fraud probabilities.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

FEATURES = ["log_amount", "ratio_to_cat_median", "robust_z", "share_of_month_cat", "ratio_to_user_p95",
            "source_rarity", "same_day_same_cat"]
NOT_SCORED = {"Rent", "EMI", "Investment", "Insurance", "Card Payment", "Transfer", "Subscriptions"}  # fixed/recurring or not spending


def build_features(tx: pd.DataFrame) -> pd.DataFrame:
    t = tx[(tx["type"] == "debit") & (~tx["category"].isin(NOT_SCORED))].copy()
    t["date"] = pd.to_datetime(t["date"])
    t["month"] = t["date"].dt.to_period("M")
    g = t.groupby(["user_id", "category"])["amount"]
    t["cat_median"] = g.transform("median")
    iqr = (g.transform(lambda s: s.quantile(0.75)) - g.transform(lambda s: s.quantile(0.25))).replace(0, np.nan)
    t["log_amount"] = np.log1p(t["amount"])
    t["ratio_to_cat_median"] = t["amount"] / t["cat_median"].replace(0, np.nan)
    t["robust_z"] = (t["amount"] - t["cat_median"]) / iqr
    t["share_of_month_cat"] = t["amount"] / t.groupby(["user_id", "month", "category"])["amount"].transform("sum")
    t["ratio_to_user_p95"] = t["amount"] / t.groupby("user_id")["amount"].transform(lambda s: s.quantile(0.95))
    src = t["card_id"].fillna(-1).astype(int).astype(str) + "|" + t["account_id"].fillna(-1).astype(int).astype(str)
    t["source"] = src
    t["source_rarity"] = 1 - t.groupby(["user_id", "source"])["amount"].transform("count") / t.groupby("user_id")["amount"].transform("count")
    t["same_day_same_cat"] = t.groupby(["user_id", "date", "category"])["amount"].transform("count")
    t[FEATURES] = t[FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return t


def rule_baseline(f: pd.DataFrame) -> np.ndarray:
    """What you would write without ML: flag anything over 3x the user's usual amount in that category."""
    return (f["ratio_to_cat_median"] > 3).to_numpy()


def train(pop: dict, seed: int = 7) -> tuple[dict, dict]:
    f = build_features(pop["transactions"])
    users = np.sort(f["user_id"].unique())
    rng = np.random.default_rng(seed)
    test_users = set(rng.choice(users, size=len(users) // 5, replace=False).tolist())
    tr, te = f[~f["user_id"].isin(test_users)], f[f["user_id"].isin(test_users)]
    contamination = 0.015  # fixed prior for "share of unusual transactions"; not tuned on labels
    model = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed, n_jobs=4).fit(tr[FEATURES])
    y = te["injected_anomaly_label"].astype(bool).to_numpy()
    pred = model.predict(te[FEATURES]) == -1
    score = -model.score_samples(te[FEATURES])
    rule = rule_baseline(te)

    def m(p):
        return {"precision": round(float(precision_score(y, p, zero_division=0)), 3),
                "recall": round(float(recall_score(y, p, zero_division=0)), 3),
                "f1": round(float(f1_score(y, p, zero_division=0)), 3), "flagged": int(p.sum())}

    hist, edges = np.histogram(score, bins=30)
    mi, mr = m(pred), m(rule)
    metrics = {
        "model": "IsolationForest", "n_estimators": 300, "contamination": contamination, "features": FEATURES,
        "training_transactions": int(len(tr)), "training_users": int(len(users) - len(test_users)),
        "test_transactions": int(len(te)), "test_users": int(len(test_users)), "planted_anomalies_in_test": int(y.sum()),
        "isolation_forest": {**mi, "pr_auc": round(float(average_precision_score(y, score)), 3)},
        "baseline_rule_3x_category_median": mr,
        "beats_rule_on_f1": mi["f1"] > mr["f1"],
        "score_distribution": {"bin_edges": [round(float(e), 4) for e in edges], "counts": hist.tolist(),
                               "threshold": round(float(-model.offset_), 4)},
        "limitations": "Evaluated on held-out SYNTHETIC users against planted (controlled) anomalies. This shows the model "
                       "recovers unusual amounts; it is not a real-world fraud-detection accuracy.",
    }
    return {"model": model}, metrics


def _severity(ratio: float, share: float) -> str:
    """Documented thresholds: high >= 8x usual, medium >= 4x, otherwise low."""
    return "high" if ratio >= 8 else "medium" if ratio >= 4 else "low"


def _distribution(scores: np.ndarray, threshold: float, bins: int = 20) -> dict:
    """Histogram of this person's anomaly scores and the model's own decision threshold (scores above it are flagged)."""
    lo, hi = float(min(scores.min(), threshold)), float(max(scores.max(), threshold))
    counts, edges = np.histogram(scores, bins=bins, range=(lo, hi))
    return {"bins": [{"from": round(float(edges[i]), 4), "to": round(float(edges[i + 1]), 4), "count": int(c)} for i, c in enumerate(counts)],
            "threshold": round(threshold, 4), "scored": int(len(scores))}


def analyse(art: dict, ident) -> dict:
    tx = ident.transactions.copy()
    tx["user_id"] = ident.uid
    f = build_features(tx)
    if f.empty:
        return {"transactions_scored": 0, "flagged_count": 0, "flagged": [], "by_category": []}
    feats = art.get("features", FEATURES)
    f["score"] = -art["model"].score_samples(f[feats])
    f["flag"] = art["model"].predict(f[feats]) == -1
    acct = {a["id"]: f"{a['bank_name']} {a['account_masked']}" for a in ident.accounts}
    card = {c["id"]: f"{c['issuer']} {c['card_name']} ••{c['last4']}" for c in ident.cards}
    cat_max = f.groupby("category")["amount"].transform("max")
    flagged = []
    for idx, r in f[f["flag"]].sort_values("score", ascending=False).iterrows():
        ratio = float(r["ratio_to_cat_median"])
        source = card.get(int(r["card_id"])) if pd.notna(r["card_id"]) else acct.get(int(r["account_id"])) if pd.notna(r["account_id"]) else "Unknown"
        reasons = [f"₹{r['amount']:,.0f} is {ratio:.1f}× your typical {r['category']} transaction (median ₹{r['cat_median']:,.0f})."]
        if r["amount"] >= cat_max.loc[idx]:
            reasons.append(f"Largest {r['category']} transaction in the last 12 months.")
        if r["share_of_month_cat"] >= 0.5:
            reasons.append(f"{r['share_of_month_cat'] * 100:.0f}% of that month's {r['category']} spending in one transaction.")
        if r["source_rarity"] >= 0.85:
            reasons.append(f"Made from a rarely used source ({source}).")
        if r["same_day_same_cat"] >= 4:
            reasons.append(f"{int(r['same_day_same_cat'])} {r['category']} transactions on the same day.")
        flagged.append({
            "transaction_id": r["ref"], "date": str(r["date"].date()), "category": r["category"],
            "merchant": r.get("merchant"), "description": r["raw_description"], "source": source,
            "amount": round(float(r["amount"]), 2), "typical_amount": round(float(r["cat_median"]), 2),
            "times_typical": round(ratio, 1), "anomaly_score": round(float(r["score"]), 4),
            "severity": _severity(ratio, float(r["share_of_month_cat"])), "reasons": reasons,
        })
    fl = pd.DataFrame(flagged)
    by_cat = [] if fl.empty else [{"category": c, "count": int(g["amount"].count()), "amount": round(float(g["amount"].sum()), 2)}
                                  for c, g in fl.groupby("category")]
    monthly = f.groupby(f["date"].dt.to_period("M").astype(str))["flag"].sum()
    return {
        "transactions_scored": int(len(f)), "flagged_count": len(flagged),
        "flagged_amount_total": round(sum(x["amount"] for x in flagged), 2),
        "flagged": flagged, "by_category": by_cat,
        "by_month": [{"month": k, "flagged": int(v)} for k, v in monthly.items()],
        "scores": {r["ref"]: round(float(r["score"]), 4) for _, r in f.iterrows()},
        "score_distribution": _distribution(f["score"].to_numpy(), float(-art["model"].offset_)),
        "severity_rule": "high: 8x+ your typical amount in that category; medium: 4x+; low: otherwise.",
        "disclaimer": "Unusual does not mean fraudulent. These are transactions worth a second look, not fraud probabilities.",
        "model_note": art.get("deployment_label"),
    }

"""Unusual-spending detector (Isolation Forest, unchanged architecture) on REAL cardholder histories: Oklahoma purchase cards.

Part A (deployed model): trained on FY2021-FY2023 cardholder histories, applied chronologically to FY2024. There are NO
fraud labels in this data. What is measured without labels: flag rate on the later year, stability of the flagged set across
random seeds, and agreement with the simple rule. Part B: a blinded, stratified sample of FY2024 transactions for human
review (perceived unusualness, NOT confirmed fraud) - written here, labelled only by people through the review interface.
Part C (separate, never presented as the deployed model's accuracy): see anomaly_ulb.py.

Features are the deployed ones that transfer across people and currencies (ratios to the person's own history):
  ratio_to_cat_median, robust_z, share_of_month_cat, ratio_to_user_p95, same_day_same_cat
Dropped from the synthetic-era list: log_amount (currency-dependent: trained in USD, applied in INR) and source_rarity
(Oklahoma has one card per cardholder, so it is constant).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ..anomaly import NOT_SCORED
from ..data import pcard as PC
from ..provenance import REAL_DIR, Run, sha256, source_record

SEED = 7
FEATURES = ["ratio_to_cat_median", "robust_z", "share_of_month_cat", "ratio_to_user_p95", "same_day_same_cat"]
CONTAMINATION = 0.015           # unchanged fixed prior (no labels to tune it on)
MIN_HISTORY = 20                # cardholders with fewer debit transactions in a period are not scored (statistics unreliable)
STRATA = {"S1_model_flagged": 150, "S2_rule_flagged_only": 75, "S3_neither": 75}


def features(t: pd.DataFrame) -> pd.DataFrame:
    """Vectorised equivalent of app.ml.anomaly.build_features for (holder, date, amount, category) rows of ONE period."""
    t = t[(t["amount"] > 0) & (~t["category"].isin(NOT_SCORED))].copy()
    t = t[t.groupby("holder")["amount"].transform("count") >= MIN_HISTORY]
    t["month"] = t["date"].dt.to_period("M")
    q = t.groupby(["holder", "category"])["amount"].quantile([0.25, 0.5, 0.75]).unstack()
    q.columns = ["q25", "cat_median", "q75"]
    t = t.join(q, on=["holder", "category"])
    t = t.join(t.groupby("holder")["amount"].quantile(0.95).rename("p95"), on="holder")
    t["ratio_to_cat_median"] = t["amount"] / t["cat_median"].replace(0, np.nan)
    t["robust_z"] = (t["amount"] - t["cat_median"]) / (t["q75"] - t["q25"]).replace(0, np.nan)
    t["share_of_month_cat"] = t["amount"] / t.groupby(["holder", "month", "category"])["amount"].transform("sum")
    t["ratio_to_user_p95"] = t["amount"] / t["p95"].replace(0, np.nan)
    t["same_day_same_cat"] = t.groupby(["holder", "date", "category"])["amount"].transform("count")
    t[FEATURES] = t[FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return t


def _fit(X, seed):
    return IsolationForest(n_estimators=300, contamination=CONTAMINATION, random_state=seed, n_jobs=4).fit(X)


def _jaccard(a: np.ndarray, b: np.ndarray) -> float:
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def review_sample(te: pd.DataFrame, flag: np.ndarray, rule: np.ndarray, score: np.ndarray, seed: int = SEED) -> tuple[list[dict], dict]:
    """Stratified random sample for BLINDED human review. Strata and selection probabilities are kept for estimation;
    the items shown to reviewers contain no score, flag or stratum."""
    rng = np.random.default_rng(seed)
    strata = np.where(flag, "S1_model_flagged", np.where(rule, "S2_rule_flagged_only", "S3_neither"))
    items, design = [], {}
    for s, n in STRATA.items():
        idx = np.flatnonzero(strata == s)
        take = rng.choice(idx, size=min(n, len(idx)), replace=False)
        design[s] = {"population": int(len(idx)), "sampled": int(len(take)),
                     "selection_probability": float(len(take) / len(idx)) if len(idx) else 0.0}
        for i in take:
            r = te.iloc[i]
            hist = te[(te["holder"] == r["holder"]) & (te["category"] == r["category"])]["amount"]
            items.append({"stratum": s, "selection_probability": design[s]["selection_probability"],
                          "hidden": {"score": round(float(score[i]), 5), "model_flag": bool(flag[i]), "rule_flag": bool(rule[i])},
                          "shown": {"date": str(r["date"].date()), "merchant": r["merchant"], "merchant_category": r["mcc"],
                                    "category": r["category"], "amount": round(float(r["amount"]), 2),
                                    "holder_category_history": {"transactions": int(len(hist)),
                                                                "median": round(float(hist.median()), 2),
                                                                "p25": round(float(hist.quantile(.25)), 2),
                                                                "p75": round(float(hist.quantile(.75)), 2),
                                                                "max_other": round(float(hist.drop(r.name, errors="ignore").max()
                                                                                         if len(hist) > 1 else 0), 2)},
                                    "holder_transactions_that_month": int(((te["holder"] == r["holder"]) & (te["month"] == r["month"])).sum()),
                                    "same_day_same_category": int(r["same_day_same_cat"])}})
    order = rng.permutation(len(items))                  # reviewers see a random order, so strata cannot be inferred
    items = [dict(items[i], item_id=f"r{k + 1:03d}") for k, i in enumerate(order)]
    return items, design


def train(approved: bool) -> tuple[str, dict]:
    run = Run("anomaly", "python -m app.ml.train anomaly")
    ok, ok_rep = PC.load_oklahoma()
    cat = ok["mcc"].map(PC.map_mcc).fillna("Other")      # Finora merchant category; unmapped MCCs grouped as 'Other'
    ok = ok.assign(category=cat)
    tr = features(ok[ok["fiscal_year"] <= 2023])
    te = features(ok[ok["fiscal_year"] == 2024]).reset_index(drop=True)
    model = _fit(tr[FEATURES], SEED)
    flag = model.predict(te[FEATURES]) == -1
    score = -model.score_samples(te[FEATURES])
    rule = (te["ratio_to_cat_median"] > 3).to_numpy()
    seeds = [11, 23, 42]
    stab = [_jaccard(flag, _fit(tr[FEATURES], s).predict(te[FEATURES]) == -1) for s in seeds]
    train_flag_rate = float((model.predict(tr[FEATURES]) == -1).mean())
    test_flag_rate = float(flag.mean())
    items, design = review_sample(te, flag, rule, score)
    folder = REAL_DIR / "anomaly" / run.version          # stored with the model it was drawn from (tracked, checksummed)
    folder.mkdir(parents=True, exist_ok=True)
    sample_path = folder / "review_sample.json"
    sample_path.write_text(json.dumps({"version": run.version, "design": design, "items": items}, indent=1))
    hist, edges = np.histogram(score, bins=30)
    passed = bool(min(stab) >= 0.7 and abs(test_flag_rate - CONTAMINATION) <= 0.02)
    metrics = {
        "model": "IsolationForest", "n_estimators": 300, "contamination": CONTAMINATION, "features": FEATURES,
        "features_dropped": {"log_amount": "currency-dependent (USD training, INR use)", "source_rarity": "one card per cardholder: constant"},
        "train_period": "FY2021-FY2023 (Jul 2020 - Jun 2023)", "test_period": "FY2024 (Jul 2023 - Jun 2024), chronological",
        "training_transactions": int(len(tr)), "training_cardholders": int(tr["holder"].nunique()),
        "test_transactions": int(len(te)), "test_cardholders": int(te["holder"].nunique()),
        "min_history_per_cardholder": MIN_HISTORY,
        "flag_rate_train": round(train_flag_rate, 4), "flag_rate_test": round(test_flag_rate, 4),
        "flag_stability_jaccard_vs_seeds": {str(s): round(j, 3) for s, j in zip(seeds, stab)},
        "rule_3x_category_median_flag_rate_test": round(float(rule.mean()), 4),
        "overlap_model_and_rule_test": round(_jaccard(flag, rule), 3),
        "score_distribution": {"bin_edges": [round(float(e), 4) for e in edges], "counts": hist.tolist(),
                               "threshold": round(float(-model.offset_), 4)},
        "accuracy": "NOT MEASURED. There are no fraud or unusualness labels in this data. A blinded human review of a stratified "
                    "sample is prepared (see human_review); until people label it, no precision or recall is claimed.",
        "human_review": {"status": "awaiting reviewers", "sample_file": f"real/anomaly/{run.version}/review_sample.json", "items": len(items), "design": design,
                         "what_is_labelled": "perceived unusualness for this cardholder, not confirmed fraud"},
        "technical_checks_passed": passed,
    }
    src = source_record("oklahoma_pcard")
    prov = {
        "data_status": "real", "evaluation_passed": passed, "approved_by_owner": bool(approved),
        "deployment_label": "Unusual for you, compared with your own history. Trained on real US government cardholder histories; "
                            "no verified accuracy yet (human review pending). Not fraud detection.",
        "datasets": [{"key": "oklahoma_pcard", "role": "training (FY21-23) + chronological test (FY24)", "name": src.get("name"),
                      "publisher": src.get("publisher"), "source_url": src.get("page"), "licence": src.get("licence"),
                      "geography": "Oklahoma, USA", "collection_period": f"{ok_rep['date_from']} to {ok_rep['date_to']}",
                      "records": ok_rep["rows"], "observations": "real", "synthetic_observations": "none",
                      "files": [{"file": f["file"], "sha256": f["sha256"], "url": f["url"]} for f in src.get("files", [])],
                      "cleaning": ok_rep, "labels": "none (unsupervised)",
                      "privacy": "Cardholder names replaced by a salted one-way hash before any processing; never stored.",
                      "known_biases": "Institutional purchasing by government employees, not household spending."}],
        "methodology": "Per-cardholder relative features within each period; Isolation Forest (300 trees, contamination 0.015); "
                       "technical pass = flag-set Jaccard >= 0.7 across seeds and FY24 flag rate within 2 points of 1.5%.",
        "limitations": "Unsupervised. Unusual does not mean fraudulent. Institutional card spending differs from personal "
                       "spending. Accuracy against human judgement is unknown until the blinded review is complete.",
        "review_sample_sha256": sha256(sample_path),
        "reproducible": "python -m app.ml.train anomaly (seed 7) with the raw files above",
    }
    out = run.save({"model": model, "features": FEATURES, "deployment_label": prov["deployment_label"]}, metrics, prov)
    return run.version, {"out": str(out), **{k: metrics[k] for k in ("training_transactions", "training_cardholders",
                         "test_transactions", "flag_rate_train", "flag_rate_test", "flag_stability_jaccard_vs_seeds",
                         "rule_3x_category_median_flag_rate_test", "overlap_model_and_rule_test")}, "design": design, "passed": passed}

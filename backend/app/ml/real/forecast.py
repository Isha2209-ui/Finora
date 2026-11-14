"""Stage 1 cash-flow forecaster: XGBoost (architecture unchanged) on ONE real UK current account (MoneyVis).

The target is next month's spending relative to the trailing 6-month average (the existing design), predicted from lag
features available before that month. Evaluation is rolling-origin and strictly chronological: to predict month t the
model is trained only on months before t. Baselines on exactly the same months: 3-month moving average and last month.

This is a SINGLE-PERSON experimental model. It does not show that the model generalises to other people.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .. import forecast as FC
from ..data import moneyvis as MV
from ..provenance import Run, sha256, source_record

FEATURES = ["r_lag1", "r_lag2", "r_avg3", "r_avg12", "r_med6", "trend_3v6", "cv6", "income_ratio", "txn_ratio"]
LABELS = {k: FC.TOTAL_LABELS[k] for k in FEATURES}
FIRST_TEST = 36          # first month (index) predicted out-of-sample: needs >= 30 training rows before it


def _m(y, p):
    return {"mae": round(float(mean_absolute_error(y, p)), 2), "rmse": round(float(np.sqrt(mean_squared_error(y, p))), 2)}


def train(approved: bool) -> tuple[str, dict]:
    run = Run("forecast", "python -m app.ml.train forecast")
    tx, tx_report = MV.transactions()
    m, m_report = MV.monthly(tx)
    MV.PROCESSED.mkdir(parents=True, exist_ok=True)
    tx.to_csv(MV.PROCESSED / "transactions_clean.csv", index=False)
    m.to_csv(MV.PROCESSED / "monthly.csv", index=False)
    rows = FC.total_rows(m).reset_index(drop=True)
    rows["ratio_target"] = rows["target"] / rows["base"]
    preds = []
    for t in range(FIRST_TEST - FC.MIN_HIST, len(rows)):
        tr = rows.iloc[:t]
        mdl = FC._xgb(7).fit(tr[FEATURES], tr["ratio_target"])
        r = rows.iloc[t]
        preds.append({"month": r["month"], "actual": float(r["target"]), "xgboost": float(mdl.predict(rows.iloc[[t]][FEATURES])[0] * r["base"]),
                      "moving_average_3m": float(r["avg3"]), "last_month": float(r["lag1"]), "base": float(r["base"]),
                      "train_rows": int(len(tr))})
    p = pd.DataFrame(preds)
    xm, am, lm = _m(p["actual"], p["xgboost"]), _m(p["actual"], p["moving_average_3m"]), _m(p["actual"], p["last_month"])
    final = FC._xgb(7).fit(rows[FEATURES], rows["ratio_target"])
    resid_ratio = float(((p["actual"] - p["xgboost"]) / p["base"]).std())
    beats = xm["mae"] < am["mae"]
    metrics = {
        "task": "Next month's total spending for one person (single-person experimental model)",
        "evaluation": {"method": f"Rolling-origin, chronological: each of {len(p)} test months ({p['month'].iloc[0]} to {p['month'].iloc[-1]}) "
                                 f"is predicted by a model trained only on earlier months (first test month uses {preds[0]['train_rows']} rows).",
                       "test_months": int(len(p)), "xgboost": xm, "baseline_moving_average_3m": am, "baseline_last_month": lm,
                       "beats_moving_average_on_mae": bool(beats),
                       "mae_improvement_vs_moving_average_pct": round((am["mae"] - xm["mae"]) / am["mae"] * 100, 1) if am["mae"] else None},
        "actual_vs_predicted": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k != "base"} for r in preds],
        "features": [LABELS[f] for f in FEATURES], "currency": "GBP",
        "feature_importance": sorted([{"feature": LABELS[f], "importance": round(float(v), 4)} for f, v in zip(FEATURES, final.feature_importances_)],
                                     key=lambda x: -x["importance"]),
    }
    src = source_record("moneyvis")
    fsrc = (src.get("files") or [{}])[0]
    prov = {
        "data_status": "real", "evaluation_passed": bool(beats), "approved_by_owner": bool(approved),
        "evaluation_note": ("Acceptance criterion: XGBoost MAE below the 3-month moving average (app/ml/acceptance.py). It "
                            + ("beats" if beats else "does NOT beat") + " the 3-month moving average on MAE; this is reported as is."),
        "deployment_label": "Experimental: trained on ONE real UK person's account (MoneyVis); accuracy for other people is not established",
        "scope": "single-person", "datasets": [{
            "key": "moneyvis", "name": "MoneyVis Bank Transactions Dataset", "publisher": "Robert S. Laramee, University of Nottingham (Mendeley Data)",
            "source_url": "https://data.mendeley.com/datasets/dnxtg6n4rv/1", "doi": "10.17632/dnxtg6n4rv.1", "download_url": fsrc.get("url"),
            "publication": "Firat et al., MoneyVis: Open Bank Transaction Data for Visualization and Beyond, EuroVis 2023",
            "collection_period": f"{tx_report['date_from']} to {tx_report['date_to']}", "geography": "United Kingdom",
            "population": "ONE anonymised retail current account (names, account number and sort code replaced)",
            "records": tx_report["transactions"], "features": 10, "format": "Excel .xlsx",
            "target": "monthly spending (derived), next-month value", "observations": "real, anonymised",
            "synthetic_observations": "none", "licence": "CC BY 4.0", "file_sha256": fsrc.get("sha256"),
            "publisher_sha256_verified": fsrc.get("publisher_checksum_verified"), "downloaded": src.get("downloaded_at"),
            "cleaning": tx_report, "monthly": m_report,
            "preprocessing": "See app/ml/data/moneyvis.py: serial-date correction, spending/income definitions, partial months dropped.",
            "missing_values": "debit/credit blank means 0 for that side; 24 rows without a category are counted as spending",
            "known_biases": "One person, one UK bank, 2015-2022, GBP; includes mortgage, Amazon-heavy shopping."}],
        "methodology": "XGBRegressor (existing hyperparameters), target = next month / trailing 6-month mean, 9 lag features.",
        "limitations": "A single person's history: about 70 usable months. It cannot show that the model works for other people. "
                       "Category-level forecasts are not trained on real data and are not shown. Stage 2 (multi-person, Berka) is pending "
                       "the data owner's permission.",
        "processed_files": {"transactions_clean.csv": sha256(MV.PROCESSED / "transactions_clean.csv"), "monthly.csv": sha256(MV.PROCESSED / "monthly.csv")},
        "reproducible": "python -m app.ml.train forecast (seed 7) with the raw file above",
    }
    art = {"total": final, "features": FEATURES, "resid_ratio": resid_ratio, "category": None, "scope": "single-person"}
    out = run.save(art, metrics, prov)
    return run.version, {"out": str(out), "eval": metrics["evaluation"], "monthly": m_report, "clean": tx_report}

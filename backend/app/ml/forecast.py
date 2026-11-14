"""Cash-Flow Forecaster (XGBoost) - predicts next month's total and per-category spending.

Each training row is one (user, month) built ONLY from information available before that
month (lag features) plus a calendar flag known in advance (festive season).
To make one model work across people with very different incomes, the target is the
RATIO of next month's spend to the user's trailing 6-month average; predictions are
converted back to rupees.

Split is chronological: the last 3 months are the test set, so the model is never
trained on the future. Baselines evaluated on the same rows:
  * trailing 3-month average       * last month's value (naive)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from ..data.generator import FESTIVE, NON_EXPENSE

MIN_HIST, TEST_MONTHS = 6, 3
TOTAL_FEATURES = ["r_lag1", "r_lag2", "r_avg3", "r_avg12", "r_med6", "trend_3v6", "cv6", "income_ratio", "disc_share", "emi_share",
                  "txn_ratio", "is_festive", "prev_festive"]
TOTAL_LABELS = {"r_avg12": "12-month average vs 6-month average", "r_med6": "Typical (median) month vs average", "r_lag1": "Last month vs 6-month average", "r_lag2": "Two months ago vs 6-month average",
                "r_avg3": "Last 3 months vs 6-month average", "trend_3v6": "Recent spending trend",
                "cv6": "Spending variability", "income_ratio": "Income vs spending", "disc_share": "Discretionary share",
                "emi_share": "EMI share", "txn_ratio": "Transaction count trend", "is_festive": "Festive-season month",
                "prev_festive": "Previous month was festive"}
CATEGORIES = ["Groceries", "Dining", "Shopping", "Travel", "Fuel", "Entertainment", "Health", "Utilities", "Education", "Cash"]
CAT_FEATURES = ["r_lag1", "r_avg3", "r_avg12", "r_med6", "trend_3v6", "cv6", "share_of_total", "is_festive", "prev_festive"] + [f"c_{c}" for c in CATEGORIES]


def _festive(month: str) -> float:
    y, m = int(month[:4]), int(month[5:7])
    return 1.0 if (y, m) in FESTIVE else 0.0


def _next_month(month: str) -> str:
    return str(pd.Period(month) + 1)


def total_rows(m: pd.DataFrame, include_next: bool = False) -> pd.DataFrame:
    m = m.sort_values("month").reset_index(drop=True)
    rows = []
    for t in range(MIN_HIST, len(m) + (1 if include_next else 0)):
        h = m.iloc[:t]
        e = h["expenses"]
        base = e.iloc[-6:].mean()
        if base <= 0:
            continue
        month = m.iloc[t]["month"] if t < len(m) else _next_month(m.iloc[-1]["month"])
        rows.append({
            "month": month, "base": base, "avg3": e.iloc[-3:].mean(), "lag1": e.iloc[-1],
            "r_lag1": e.iloc[-1] / base, "r_lag2": e.iloc[-2] / base, "r_avg3": e.iloc[-3:].mean() / base,
            "r_avg12": e.iloc[-12:].mean() / base, "r_med6": e.iloc[-6:].median() / base,
            "trend_3v6": e.iloc[-3:].mean() / e.iloc[-6:-3].mean() if e.iloc[-6:-3].mean() > 0 else 1.0,
            "cv6": e.iloc[-6:].std() / base, "income_ratio": h["income"].iloc[-3:].mean() / base,
            "disc_share": h["discretionary"].iloc[-3:].sum() / max(e.iloc[-3:].sum(), 1.0),
            "emi_share": h["emi"].iloc[-3:].sum() / max(e.iloc[-3:].sum(), 1.0),
            "txn_ratio": h["txn_count"].iloc[-1] / max(h["txn_count"].iloc[-6:].mean(), 1.0),
            "is_festive": _festive(month), "prev_festive": _festive(h["month"].iloc[-1]),
            "target": m.iloc[t]["expenses"] if t < len(m) else np.nan,
        })
    return pd.DataFrame(rows)


def category_matrix(tx: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    t = tx[~tx["category"].isin(NON_EXPENSE)].copy()
    t["month"] = pd.to_datetime(t["date"]).dt.to_period("M").astype(str)
    t["spend"] = np.where(t["type"] == "credit", -t["amount"], t["amount"])
    mat = t.pivot_table(index="month", columns="category", values="spend", aggfunc="sum", fill_value=0.0)
    return mat.reindex(index=months, columns=CATEGORIES, fill_value=0.0).clip(lower=0.0)


def category_rows(mat: pd.DataFrame, include_next: bool = False) -> pd.DataFrame:
    months = list(mat.index)
    total = mat.sum(axis=1)
    rows = []
    for t in range(MIN_HIST, len(months) + (1 if include_next else 0)):
        month = months[t] if t < len(months) else _next_month(months[-1])
        tot_base = total.iloc[t - 6:t].mean()
        for c in CATEGORIES:
            s = mat[c].iloc[:t]
            base = s.iloc[-6:].mean()
            if base < 300:  # ignore categories the person hardly uses
                continue
            row = {"month": month, "category": c, "base": base, "avg3": s.iloc[-3:].mean(), "lag1": s.iloc[-1],
                   "r_lag1": s.iloc[-1] / base, "r_avg3": s.iloc[-3:].mean() / base,
                   "r_avg12": s.iloc[-12:].mean() / base, "r_med6": s.iloc[-6:].median() / base,
                   "trend_3v6": s.iloc[-3:].mean() / s.iloc[-6:-3].mean() if s.iloc[-6:-3].mean() > 0 else 1.0,
                   "cv6": s.iloc[-6:].std() / base, "share_of_total": base / max(tot_base, 1.0),
                   "is_festive": _festive(month), "prev_festive": _festive(months[t - 1]),
                   "target": mat[c].iloc[t] if t < len(months) else np.nan}
            for cc in CATEGORIES:
                row[f"c_{cc}"] = 1.0 if cc == c else 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def _xgb(seed):
    return XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.04, subsample=0.85, colsample_bytree=0.85,
                        min_child_weight=8, reg_lambda=2.0, objective="reg:absoluteerror", random_state=seed, n_jobs=4)


def _m(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = y > 0
    return {"mae": round(float(mean_absolute_error(y, p)), 1), "rmse": round(float(np.sqrt(mean_squared_error(y, p))), 1),
            "mape_pct": round(float(np.mean(np.abs(y[ok] - p[ok]) / y[ok]) * 100), 2)}


def train(pop: dict, seed: int = 7) -> tuple[dict, dict]:
    tot, cat = [], []
    tx = pop["transactions"]
    for uid, m in pop["monthly"].groupby("user_id"):
        r = total_rows(m)
        r["user_id"] = uid
        tot.append(r)
        c = category_rows(category_matrix(tx[tx["user_id"] == uid], sorted(m["month"])))
        c["user_id"] = uid
        cat.append(c)
    tot, cat = pd.concat(tot, ignore_index=True), pd.concat(cat, ignore_index=True)
    months = sorted(tot["month"].unique())
    test_m = set(months[-TEST_MONTHS:])

    tr, te = tot[~tot["month"].isin(test_m)], tot[tot["month"].isin(test_m)]
    model = _xgb(seed).fit(tr[TOTAL_FEATURES], tr["target"] / tr["base"])
    pred = model.predict(te[TOTAL_FEATURES]) * te["base"]
    mx, b3, b1 = _m(te["target"], pred), _m(te["target"], te["avg3"]), _m(te["target"], te["lag1"])
    resid_ratio = float(np.std((te["target"] - pred) / te["base"]))
    pi = permutation_importance(model, te[TOTAL_FEATURES], te["target"] / te["base"], n_repeats=8, random_state=seed)
    imp = sorted(zip(TOTAL_FEATURES, pi.importances_mean.tolist()), key=lambda kv: -kv[1])
    by_month = [{"month": mth, **{"xgboost_mae": _m(g["target"], model.predict(g[TOTAL_FEATURES]) * g["base"])["mae"],
                                  "baseline_3m_mae": _m(g["target"], g["avg3"])["mae"], "festive": bool(_festive(mth))}}
                for mth, g in te.groupby("month")]

    ctr, cte = cat[~cat["month"].isin(test_m)], cat[cat["month"].isin(test_m)]
    cmodel = _xgb(seed).fit(ctr[CAT_FEATURES], (ctr["target"] / ctr["base"]).clip(0, 6))
    cpred = np.clip(cmodel.predict(cte[CAT_FEATURES]), 0, None) * cte["base"]
    cx, cb = _m(cte["target"], cpred), _m(cte["target"], cte["avg3"])
    per_cat = []
    for c, g in cte.assign(pred=cpred).groupby("category"):
        per_cat.append({"category": c, "xgboost_mae": _m(g["target"], g["pred"])["mae"], "baseline_3m_mae": _m(g["target"], g["avg3"])["mae"]})

    metrics = {
        "model": "XGBRegressor (target = next month / trailing 6-month average)",
        "split": {"type": "chronological", "train_months": [months[0], months[-TEST_MONTHS - 1]], "test_months": sorted(test_m)},
        "total_expense": {"train_rows": int(len(tr)), "test_rows": int(len(te)), "xgboost": mx,
                          "baseline_3_month_average": b3, "baseline_last_month": b1,
                          "beats_baseline": mx["mae"] < b3["mae"],
                          "improvement_vs_3m_average_pct": round((b3["mae"] - mx["mae"]) / b3["mae"] * 100, 1),
                          "by_test_month": by_month,
                          "permutation_importance": [{"feature": TOTAL_LABELS[f], "importance": round(v, 4)} for f, v in imp]},
        "category_expense": {"train_rows": int(len(ctr)), "test_rows": int(len(cte)), "xgboost": cx,
                             "baseline_3_month_average": cb, "beats_baseline": cx["mae"] < cb["mae"],
                             "improvement_vs_3m_average_pct": round((cb["mae"] - cx["mae"]) / cb["mae"] * 100, 1),
                             "per_category": per_cat},
        "limitations": "Trained on synthetic spending histories. Month-to-month personal spending is noisy, so errors of "
                       "10-15% are normal; importance scores show association, not causation.",
    }
    return {"total": model, "category": cmodel, "resid_ratio": resid_ratio}, metrics


def analyse(art: dict, ident, monthly: pd.DataFrame, snap: dict) -> dict:
    m = monthly.sort_values("month").reset_index(drop=True)
    rows = total_rows(m, include_next=True)
    if rows.empty:
        return {"available": False, "note": f"Need at least {MIN_HIST} months of history to forecast."}
    feats = art.get("features", TOTAL_FEATURES)
    rows["pred"] = art["total"].predict(rows[feats]) * rows["base"]
    nxt, hist = rows.iloc[-1], rows.iloc[:-1]
    predicted = float(nxt["pred"])
    band = 1.28 * art["resid_ratio"] * float(nxt["base"])  # ~80% interval from held-out residuals
    last = float(m["expenses"].iloc[-1])

    mat = category_matrix(ident.transactions, list(m["month"]))
    crow = category_rows(mat, include_next=True)
    cats = []
    if not crow.empty and art.get("category") is not None:
        crow["pred"] = np.clip(art["category"].predict(crow[CAT_FEATURES]), 0, None) * crow["base"]
        for _, r in crow[crow["month"] == nxt["month"]].sort_values("pred", ascending=False).iterrows():
            chg = (r["pred"] - r["avg3"]) / r["avg3"] * 100 if r["avg3"] > 0 else None
            cats.append({"category": r["category"], "predicted": round(float(r["pred"])), "last_month": round(float(r["lag1"])),
                         "three_month_avg": round(float(r["avg3"])), "change_vs_3m_avg_pct": None if chg is None else round(float(chg), 1),
                         "suggested_budget": round(float(min(r["pred"], r["base"])) * 0.9, -2),
                         "trend": "rising" if chg and chg > 8 else "falling" if chg and chg < -8 else "steady"})
    # scale flexible categories so they are consistent with the total forecast's fixed part
    cf = snap["cash_flow"]
    exp_income = cf["avg_monthly_income"] if ident.user["employment_type"] != "salaried" else float(m["income"].tail(3).median())
    invest = float(m["invested"].tail(3).mean())
    surplus = exp_income - predicted
    bank = sum(a["balance"] for a in ident.accounts)
    err = (hist["target"] - hist["pred"]).abs()
    drivers = sorted([c for c in cats if (c["change_vs_3m_avg_pct"] or 0) > 0], key=lambda c: -(c["predicted"] - c["three_month_avg"]))[:3]
    return {
        "available": True, "prediction_month": nxt["month"], "festive_month": bool(nxt["is_festive"]),
        "predicted_total_expense": round(predicted),
        "range": {"low": round(predicted - band), "high": round(predicted + band), "confidence": "about 80%, from held-out errors"},
        "last_month_actual": round(last), "three_month_avg": round(float(nxt["avg3"])),
        "change_vs_last_month": round(predicted - last), "change_vs_last_month_pct": round((predicted - last) / last * 100, 1) if last else None,
        "expected_income": round(exp_income), "projected_surplus": round(surplus),
        "projected_status": "surplus" if surplus >= 0 else "deficit",
        "planned_investments": round(invest),
        "projected_bank_balance_end_of_month": round(bank + surplus - invest),
        "current_bank_balance": round(bank),
        "cash_crunch_warning": bool(bank + surplus - invest < 0.5 * predicted),
        "category_predictions": cats, "top_increase_drivers": [d["category"] for d in drivers],
        "actual_vs_predicted": [{"month": r["month"], "actual": round(float(r["target"])), "predicted": round(float(r["pred"]))} for _, r in hist.iterrows()],
        "backtest_on_this_person": {"months": int(len(hist)), "mae": round(float(err.mean())) if len(hist) else None,
                                    "note": "Demo identities are never used for training, so this is an out-of-sample check."},
        "model_scope": art.get("scope", "legacy"),
        "category_forecast_available": art.get("category") is not None,
        "model_note": ("Experimental model trained on ONE real person's UK bank account (MoneyVis). It has not been shown to "
                       "work for other people; per-category forecasts are not shown because no real data trains them."
                       if art.get("scope") == "single-person" else None),
    }

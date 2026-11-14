"""Statement Intelligence: where the money goes, how it changes, who it goes to, what repeats, what is invested and where
income comes from - computed from the same cleaned transactions the rest of Finora uses (cleaning.clean_transactions),
for demo, sandbox, manual and imported data alike.

All figures are deterministic aggregations of the person's rows. Nothing is estimated or filled in: a section with no
data says so. "Unusual" means statistically unusual for this person, never "fraud".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.generator import DISCRETIONARY, ESSENTIAL, NON_EXPENSE
from .cleaning import clean_transactions
from .loader import Identity
from .statement_classify import merchant_name

TOP_CATEGORIES = 8
CADENCES = [("weekly", 5, 9, 52 / 12), ("fortnightly", 12, 17, 26 / 12), ("monthly", 25, 36, 1.0), ("quarterly", 80, 100, 1 / 3),
            ("half-yearly", 170, 195, 1 / 6), ("yearly", 340, 390, 1 / 12)]


def _r(x, nd=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def build(ident: Identity, *, months: int | None = None, account_id: int | None = None, card_id: int | None = None) -> dict:
    tx = ident.transactions.copy()
    inc = ident.income.copy()
    if account_id is not None:
        tx = tx[tx["account_id"] == account_id]
        inc = inc[inc["account_id"] == account_id] if "account_id" in inc else inc.iloc[0:0]
    if card_id is not None:
        tx = tx[tx["card_id"] == card_id]
        inc = inc.iloc[0:0]
    if tx.empty and inc.empty:
        return {"available": False, "reason": "No transactions or income for this selection yet. Import a statement or add transactions.",
                "filters": _filters(ident, account_id, card_id)}
    t, _ = clean_transactions(tx) if len(tx) else (pd.DataFrame(columns=["date", "month", "amount", "type", "category", "spend",
                                                                         "raw_description", "is_one_time_large"]), {})
    inc = inc.assign(date=pd.to_datetime(inc["date"]))
    inc["month"] = inc["date"].dt.to_period("M").astype(str)
    all_months = sorted(set(t["month"]) | set(inc["month"])) if len(t) or len(inc) else []
    if months:
        keep = set(all_months[-months:])
        t, inc = t[t["month"].isin(keep)], inc[inc["month"].isin(keep)]
        all_months = [m for m in all_months if m in keep]
    if len(t):
        names = t["merchant"] if "merchant" in t else pd.Series(None, index=t.index)
        t["merchant_name"] = [m if isinstance(m, str) and m.strip() else merchant_name(d) for m, d in zip(names, t["raw_description"])]
    spend_known, income_known = bool(len(t)), bool(len(inc))
    out = {"available": True, "filters": _filters(ident, account_id, card_id),
           "coverage": _coverage(t, inc, all_months, ident),
           "where": _where(t, all_months) if spend_known else None,
           "trend": _trend(t, inc, all_months, spend_known, income_known),
           "changes": _changes(t, all_months) if spend_known else None,
           "merchants": _merchants(t) if spend_known else [],
           "recurring": _recurring(t, ident) if spend_known else {"items": [], "monthly_total": 0},
           "investments": _investments(t, ident, all_months) if spend_known else None,
           "income": _income(inc, all_months) if income_known else None,
           "unusual": _unusual(t, all_months) if spend_known else None,
           "review": _review(ident, tx, inc),
           "notes": ["Spending excludes transfers between your own accounts, credit-card bill payments (card spends are counted "
                     "instead) and investments; refunds reduce the category they came from.",
                     "Investment flows are money moved into or out of investments, not verified holdings.",
                     "Unusual means unusual for you, judged statistically; it is not fraud detection."]}
    if not income_known:
        out["notes"].append("No income records in this selection, so savings and income patterns are not shown.")
    return out


def _filters(ident: Identity, account_id, card_id) -> dict:
    return {"account_id": account_id, "card_id": card_id,
            "accounts": [{"id": a["id"], "label": f"{a['bank_name']} {a['account_masked']}"} for a in ident.accounts],
            "cards": [{"id": c["id"], "label": f"{c['issuer']} {c['card_name']} ••{c['last4']}"} for c in ident.cards]}


def _coverage(t, inc, months, ident) -> dict:
    src = t["category_source"].fillna("given") if "category_source" in t else pd.Series(dtype=str)
    imported = int(t["import_id"].notna().sum()) if "import_id" in t else 0
    dmin = min([d for d in [t["date"].min() if len(t) else None, inc["date"].min() if len(inc) else None] if d is not None and not pd.isna(d)], default=None)
    dmax = max([d for d in [t["date"].max() if len(t) else None, inc["date"].max() if len(inc) else None] if d is not None and not pd.isna(d)], default=None)
    partial = []
    if dmin is not None and dmin.day > 3:
        partial.append(dmin.strftime("%Y-%m"))
    if dmax is not None and dmax.day < 26:
        partial.append(dmax.strftime("%Y-%m"))
    return {"months": len(months), "from": dmin.date().isoformat() if dmin is not None else None,
            "to": dmax.date().isoformat() if dmax is not None else None, "transactions": int(len(t)), "income_records": int(len(inc)),
            "imported_transactions": imported, "categorised_by_model": int((src == "model").sum()),
            "corrected_by_you": int((src == "user").sum()), "partial_months": sorted(set(partial)),
            "kind": ident.user.get("kind")}


def _where(t, months) -> dict:
    s = t[t["spend"] != 0]
    by = s.groupby("category")["spend"].sum()
    by = by[by > 0].sort_values(ascending=False)
    total = float(by.sum())
    n = max(1, len(months))
    groups = {"Essentials": float(by[by.index.isin(ESSENTIAL)].sum()), "Lifestyle": float(by[by.index.isin(DISCRETIONARY)].sum()),
              "Loan EMIs": float(by.get("EMI", 0.0)), "Cash withdrawals": float(by.get("Cash", 0.0))}
    groups["Other"] = max(0.0, total - sum(groups.values()))
    refunds = float(-t[(t["type"] == "credit") & (t["spend"] < 0)]["spend"].sum())
    return {"total_spend": _r(total), "avg_monthly_spend": _r(total / n), "refunds": _r(refunds),
            "categories": [{"category": c, "total": _r(v), "share_pct": _r(v / total * 100, 1) if total else None, "per_month": _r(v / n),
                            "kind": "essential" if c in ESSENTIAL else "lifestyle" if c in DISCRETIONARY else "other"}
                           for c, v in by.items()],
            "groups": [{"group": g, "total": _r(v), "share_pct": _r(v / total * 100, 1) if total else None} for g, v in groups.items() if v > 0]}


def _trend(t, inc, months, spend_known, income_known) -> dict:
    rows = []
    top = []
    if spend_known:
        s = t[t["spend"] != 0]
        tot = s.groupby("category")["spend"].sum().sort_values(ascending=False)
        top = [c for c in tot.index if tot[c] > 0][:TOP_CATEGORIES]
        piv = s.assign(cat=s["category"].where(s["category"].isin(top), "Other")).pivot_table(
            index="month", columns="cat", values="spend", aggfunc="sum", fill_value=0.0)
    for m in months:
        row = {"month": m}
        if spend_known:
            vals = piv.loc[m] if m in piv.index else pd.Series(dtype=float)
            for c in top + (["Other"] if "Other" in piv.columns else []):
                row[c] = _r(max(0.0, float(vals.get(c, 0.0))))
            row["spend"] = _r(float(t[t["month"] == m]["spend"].sum()))
            row["invested"] = _r(float(t[(t["month"] == m) & (t["category"] == "Investment") & (t["type"] == "debit")]["amount"].sum()))
        if income_known:
            row["income"] = _r(float(inc[inc["month"] == m]["amount"].sum()))
        if spend_known and income_known:
            row["saved"] = _r(row["income"] - row["spend"])
        rows.append(row)
    return {"series": top + (["Other"] if spend_known and len(t[t["spend"] != 0]["category"].unique()) > len(top) else []),
            "months": rows}


def _changes(t, months) -> dict | None:
    if len(months) < 2:
        return {"available": False, "reason": "Needs at least two months of transactions."}
    w = 3 if len(months) >= 6 else 1
    recent, prior = months[-w:], months[-2 * w:-w]
    s = t[t["spend"] != 0]
    a = s[s["month"].isin(recent)].groupby("category")["spend"].sum() / w
    b = s[s["month"].isin(prior)].groupby("category")["spend"].sum() / w
    cats = sorted(set(a.index) | set(b.index))
    rows = []
    for c in cats:
        x, y = float(a.get(c, 0.0)), float(b.get(c, 0.0))
        if max(x, y) < 500:
            continue
        rows.append({"category": c, "recent_per_month": _r(x), "before_per_month": _r(y), "change": _r(x - y),
                     "change_pct": _r((x - y) / y * 100, 1) if y > 0 else None})
    rows.sort(key=lambda r: -abs(r["change"]))
    out = {"available": True, "window_months": w, "recent": recent, "before": prior, "categories": rows[:12],
           "total_recent_per_month": _r(float(a.sum())), "total_before_per_month": _r(float(b.sum()))}
    if len(months) >= 13:
        last, year_ago = months[-1], months[-13]
        out["year_over_year"] = {"month": last, "compared_with": year_ago,
                                 "spend": _r(float(s[s["month"] == last]["spend"].sum())),
                                 "spend_year_ago": _r(float(s[s["month"] == year_ago]["spend"].sum()))}
    return out


def _merchants(t, k: int = 15) -> list[dict]:
    s = t[(t["type"] == "debit") & ~t["category"].isin(NON_EXPENSE)]
    if s.empty:
        return []
    total = float(s["amount"].sum())
    g = s.groupby("merchant_name").agg(total=("amount", "sum"), count=("amount", "size"), avg=("amount", "mean"),
                                       months=("month", "nunique"), last=("date", "max"),
                                       category=("category", lambda c: c.value_counts().index[0]))
    g = g.sort_values("total", ascending=False).head(k)
    return [{"merchant": m, "category": r.category, "total": _r(r.total), "count": int(r["count"]), "avg_ticket": _r(r["avg"]),
             "months_active": int(r.months), "last_date": r.last.date().isoformat(), "share_pct": _r(r.total / total * 100, 1)}
            for m, r in g.iterrows()]


def detect_recurring(t: pd.DataFrame, end: pd.Timestamp | None = None) -> list[dict]:
    """Repeating debits to the same counterparty at a steady interval and a steady amount."""
    # cash withdrawals are not a commitment (what the cash buys is unknown); transfers and card bills are money moved
    d = t[(t["type"] == "debit") & ~t["category"].isin(["Transfer", "Card Payment", "Cash"])]
    if d.empty:
        return []
    end = end or d["date"].max()
    out = []
    for (m, cat), g in d.groupby(["merchant_name", "category"]):
        if len(g) < 3:
            continue
        g = g.sort_values("date")
        gaps = g["date"].diff().dt.days.dropna()
        gaps = gaps[gaps > 0]
        if gaps.empty:
            continue
        med = float(gaps.median())
        cad = next((c for c in CADENCES if c[1] <= med <= c[2]), None)
        if cad is None:
            continue
        regular = float(((gaps >= cad[1]) & (gaps <= cad[2])).mean())
        amt = g["amount"]
        typical = float(amt.median())
        steady = float(((amt - typical).abs() <= 0.15 * typical).mean())
        if regular < 0.6 or steady < 0.6:
            continue
        last = g["date"].max()
        nxt = last + pd.Timedelta(days=round(med))
        active = (end - last).days <= med * 1.6
        out.append({"merchant": m, "category": cat, "cadence": cad[0], "typical_amount": _r(typical),
                    "monthly_equivalent": _r(typical * cad[3]), "occurrences": int(len(g)),
                    "first_date": g["date"].min().date().isoformat(), "last_date": last.date().isoformat(),
                    "next_expected": nxt.date().isoformat() if active else None, "status": "active" if active else "stopped",
                    "amount_steadiness_pct": _r(steady * 100, 0), "interval_regularity_pct": _r(regular * 100, 0),
                    "kind": _kind(cat)})
    return sorted(out, key=lambda r: (r["status"] != "active", -r["monthly_equivalent"]))


BILLS = {"Rent", "Utilities", "Insurance", "Education"}


def _kind(cat: str) -> str:
    return ("investment" if cat == "Investment" else "loan" if cat == "EMI" else "subscription" if cat == "Subscriptions"
            else "bill" if cat in BILLS else "regular spend")


def _recurring(t, ident) -> dict:
    items = detect_recurring(t)
    known = [str(r["name"]).upper() for r in ident.recurring]
    for it in items:
        mu = it["merchant"].upper()
        it["already_recorded"] = any(mu in k or k in mu for k in known if k)
    active = [i for i in items if i["status"] == "active"]
    return {"items": items, "active_count": len(active), "monthly_total": _r(sum(i["monthly_equivalent"] for i in active)),
            "by_kind": {k: _r(sum(i["monthly_equivalent"] for i in active if i["kind"] == k))
                        for k in ("bill", "subscription", "loan", "investment", "regular spend") if any(i["kind"] == k for i in active)}}


def _investments(t, ident, months) -> dict:
    inv = t[t["category"] == "Investment"]
    out_ = inv[inv["type"] == "debit"]
    in_ = inv[inv["type"] == "credit"]
    by_m = [{"month": m, "invested": _r(float(out_[out_["month"] == m]["amount"].sum())),
             "withdrawn": _r(float(in_[in_["month"] == m]["amount"].sum()))} for m in months]
    dest = out_.groupby("merchant_name")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False).head(10)
    n = max(1, len(months))
    return {"total_invested": _r(float(out_["amount"].sum())), "total_withdrawn": _r(float(in_["amount"].sum())),
            "net_invested": _r(float(out_["amount"].sum() - in_["amount"].sum())), "avg_monthly_invested": _r(float(out_["amount"].sum()) / n),
            "months_with_investing": int(out_["month"].nunique()), "months": by_m,
            "destinations": [{"name": k, "total": _r(v["sum"]), "count": int(v["count"])} for k, v in dest.iterrows()],
            "recorded_sips": len(ident.sips), "recorded_sip_monthly": _r(sum(s["amount"] for s in ident.sips if s.get("active", True))),
            "emi_paid": _r(float(t[(t["category"] == "EMI") & (t["type"] == "debit")]["amount"].sum())),
            "note": "These are cash flows into and out of investments seen in your transactions. They are not verified holdings; "
                    "add holdings under My Data."}


def _income(inc, months) -> dict:
    n = max(1, len(months))
    by_src = inc.groupby("source")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    total = float(inc["amount"].sum())
    monthly = [{"month": m, **{s: _r(float(inc[(inc["month"] == m) & (inc["source"] == s)]["amount"].sum())) for s in by_src.index}}
               for m in months]
    sal = inc[inc["source"] == "Salary"]
    salary = None
    if len(sal):
        per_m = sal.groupby("month")["amount"].sum()
        steps = []
        vals = per_m.values
        for i in range(1, len(vals)):
            if vals[i - 1] > 0 and abs(vals[i] - vals[i - 1]) / vals[i - 1] >= 0.05 and (i + 1 >= len(vals) or abs(vals[i + 1] - vals[i]) / vals[i] < 0.05):
                steps.append({"month": per_m.index[i], "from": _r(vals[i - 1]), "to": _r(vals[i]),
                              "change_pct": _r((vals[i] - vals[i - 1]) / vals[i - 1] * 100, 1)})
        salary = {"months_received": int(len(per_m)), "months_covered": len(months),
                  "regularity_pct": _r(len(per_m) / len(months) * 100, 0), "median_monthly": _r(float(per_m.median())),
                  "latest_monthly": _r(float(per_m.iloc[-1])), "latest_month": per_m.index[-1],
                  "typical_day": int(sal["date"].dt.day.median()), "changes": steps[-6:]}
    return {"total": _r(total), "avg_monthly": _r(total / n), "salary": salary,
            "sources": [{"source": s, "total": _r(v["sum"]), "count": int(v["count"]), "share_pct": _r(v["sum"] / total * 100, 1) if total else None}
                        for s, v in by_src.iterrows()],
            "months": monthly, "salary_share_pct": _r(float(sal["amount"].sum()) / total * 100, 1) if total else None}


def _unusual(t, months) -> dict:
    s = t[t["spend"] != 0]
    monthly = s.groupby("month")["spend"].sum().reindex(months, fill_value=0.0)
    out_months = []
    if len(monthly) >= 4:
        med = float(monthly.median())
        mad = float((monthly - med).abs().median()) or max(1.0, med * 0.1)
        for m, v in monthly.items():
            z = (v - med) / (1.4826 * mad)
            if z >= 2.5 and v - med >= 5000:
                out_months.append({"month": m, "spend": _r(v), "typical": _r(med), "above_typical": _r(v - med)})
    spikes = []
    if len(months) >= 4:
        last = months[-1]
        trail = months[-7:-1]
        cur = s[s["month"] == last].groupby("category")["spend"].sum()
        base = s[s["month"].isin(trail)].groupby("category")["spend"].sum() / max(1, len(trail))
        for c, v in cur.items():
            b = float(base.get(c, 0.0))
            if v >= 1.6 * b and v - b >= 2000:
                spikes.append({"category": c, "month": last, "spend": _r(v), "usual": _r(b), "times_usual": _r(v / b, 1) if b > 0 else None})
        spikes.sort(key=lambda r: -(r["spend"] - r["usual"]))
    big = t[t.get("is_one_time_large", False) == True].sort_values("amount", ascending=False).head(10)  # noqa: E712
    return {"months": out_months, "category_spikes": spikes[:8],
            "large_one_offs": [{"date": r.date.date().isoformat(), "description": str(r.raw_description)[:80], "category": r.category,
                                "amount": _r(r.amount)} for r in big.itertuples()],
            "method": "Months more than 2.5 robust deviations above your median month; categories at 1.6x their 6-month "
                      "average in the latest month; single purchases at least 4x their category's median and at least Rs 15,000."}


def _review(ident, tx, inc) -> dict:
    n_tx = int(tx["needs_review"].fillna(False).astype(bool).sum()) if "needs_review" in tx else 0
    n_inc = int(inc["needs_review"].fillna(False).astype(bool).sum()) if "needs_review" in inc else 0
    return {"needs_review": n_tx + n_inc, "transactions": n_tx, "income_records": n_inc}

"""Peer Benchmarking (K-Means) - "how do I compare with people who manage money like me?"

Each person in the population is summarised by 8 behaviour features computed from their
monthly history; features are standardised and clustered. k is chosen by silhouette score
over k = 2..6. Cluster names are derived from the fitted centroids (never hard-coded per id).
A new person is assigned to the nearest centroid and compared with that group and with everyone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

FEATURES = ["savings_rate", "essential_to_income", "discretionary_to_income", "emi_to_income", "invest_to_income",
            "expense_cv", "income_cv", "card_utilisation"]
LABELS = {"savings_rate": "Savings rate", "essential_to_income": "Essentials / income",
          "discretionary_to_income": "Discretionary / income", "emi_to_income": "EMI / income",
          "invest_to_income": "Investing / income", "expense_cv": "Spending variability",
          "income_cv": "Income variability", "card_utilisation": "Card utilisation"}
HIGHER_IS_BETTER = {"savings_rate": True, "invest_to_income": True, "essential_to_income": False,
                    "discretionary_to_income": False, "emi_to_income": False, "expense_cv": False, "income_cv": False,
                    "card_utilisation": False}


def user_features(monthly: pd.DataFrame, card_limit: float, card_outstanding: float) -> dict:
    inc = monthly["income"].sum()
    if inc <= 0:
        inc = 1.0
    return {
        "savings_rate": float(np.clip(monthly["savings"].sum() / inc, -1, 1)),
        "essential_to_income": monthly["essential"].sum() / inc, "discretionary_to_income": monthly["discretionary"].sum() / inc,
        "emi_to_income": monthly["emi"].sum() / inc, "invest_to_income": monthly["invested"].sum() / inc,
        "expense_cv": monthly["expenses"].std() / max(monthly["expenses"].mean(), 1.0),
        "income_cv": monthly["income"].std() / max(monthly["income"].mean(), 1.0),
        "card_utilisation": card_outstanding / card_limit if card_limit else 0.0,
    }


def _name(z: pd.Series) -> str:
    """Name a cluster from its centroid (in standard-deviation units)."""
    if z["emi_to_income"] > 0.8:
        return "Loan-Heavy"
    if z["income_cv"] > 0.8:
        return "Irregular Earners"
    if z["discretionary_to_income"] > 0.6 or z["savings_rate"] < -0.6:
        return "High Discretionary Spenders"
    if z["savings_rate"] > 0.3 and z["invest_to_income"] > 0.3:
        return "Disciplined Savers & Investors"
    if z["savings_rate"] > 0.2:
        return "Consistent Savers"
    return "Balanced Middle"


def train(pop: dict, seed: int = 7) -> tuple[dict, dict]:
    cards = pop["cards"].groupby("user_id")[["credit_limit", "outstanding"]].sum()
    rows, ids = [], []
    for uid, m in pop["monthly"].groupby("user_id"):
        lim, out = (cards.loc[uid] if uid in cards.index else (0.0, 0.0))
        rows.append(user_features(m, float(lim), float(out)))
        ids.append(uid)
    X = pd.DataFrame(rows, index=ids)[FEATURES]
    scaler = StandardScaler().fit(X)
    Z = scaler.transform(X)
    scan = []
    for k in range(2, 7):
        lab = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(Z)
        scan.append({"k": k, "silhouette": round(float(silhouette_score(Z, lab)), 4),
                     "davies_bouldin": round(float(davies_bouldin_score(Z, lab)), 4)})
    best = max(scan, key=lambda s: s["silhouette"])
    km = KMeans(n_clusters=best["k"], n_init=10, random_state=seed).fit(Z)
    cz = pd.DataFrame(km.cluster_centers_, columns=FEATURES)
    names, used = {}, {}
    for i, row in cz.iterrows():
        n = _name(row)
        used[n] = used.get(n, 0) + 1
        names[i] = n if used[n] == 1 else f"{n} ({used[n]})"
    X["cluster"] = km.labels_
    arche = pop["users"].set_index("id").loc[ids, "archetype"]
    centroids = []
    for i in range(best["k"]):
        members = X[X["cluster"] == i]
        centroids.append({"cluster": names[i], "size": int(len(members)),
                          "means": {LABELS[f]: round(float(members[f].mean()) * 100, 1) for f in FEATURES}})
    metrics = {
        "model": "KMeans", "users": int(len(X)), "features": [LABELS[f] for f in FEATURES], "k_scan": scan,
        "chosen_k": best["k"], "silhouette": best["silhouette"], "davies_bouldin": best["davies_bouldin"],
        "adjusted_rand_vs_generator_archetypes": round(float(adjusted_rand_score(arche, km.labels_)), 3),
        "clusters": centroids,
        "limitations": "Clusters describe the synthetic population. The Adjusted Rand Index compares clusters with the "
                       "generator's hidden archetypes (used for evaluation only, never as a feature).",
    }
    return {"scaler": scaler, "kmeans": km, "names": names, "population": X}, metrics


def analyse(art: dict, ident, monthly: pd.DataFrame) -> dict:
    if art.get("kind") == "scf_households":
        return _analyse_scf(art, ident, monthly)
    lim = sum(c["credit_limit"] for c in ident.cards)
    out = sum(c["outstanding"] for c in ident.cards)
    feats = user_features(monthly, lim, out)
    x = pd.DataFrame([feats])[FEATURES]
    k = int(art["kmeans"].predict(art["scaler"].transform(x))[0])
    pop = art["population"]
    peers = pop[pop["cluster"] == k]
    comp, strengths, weaknesses = [], [], []
    for f in FEATURES:
        pct_all = float((pop[f] < feats[f]).mean() * 100)
        better_than = pct_all if HIGHER_IS_BETTER[f] else 100 - pct_all
        comp.append({"metric": LABELS[f], "you": round(feats[f] * 100, 1), "peer_group_median": round(float(peers[f].median()) * 100, 1),
                     "everyone_median": round(float(pop[f].median()) * 100, 1), "better_than_pct_of_people": round(better_than)})
        if better_than >= 70:
            strengths.append(LABELS[f])
        elif better_than <= 30:
            weaknesses.append(LABELS[f])
    return {"peer_group": art["names"][k], "peer_group_size": int(len(peers)), "population_size": int(len(pop)),
            "comparison": comp, "strengths": strengths, "weaknesses": weaknesses,
            "all_groups": [{"name": art["names"][i], "size": int((pop["cluster"] == i).sum())} for i in sorted(art["names"])],
            "note": "Compared with a synthetic population of users; values are percentages of income unless stated."}


# ---------------------------------------------------------------- real-data peers (Federal Reserve SCF 2022, Phase 6)
def scf_profile_features(ident, monthly: pd.DataFrame) -> dict | None:
    """The same 8 ratios as the SCF model, computed from a Finora profile's own records with the SCF definitions where Finora
    has the data (verified 2026-11-15). None if income is unknown.
      liquid       SCF LIQ = transaction accounts only (no CDs/FDs, no cash in hand)   -> bank balances
      financial    SCF FIN = LIQ + CDs + funds + stocks + bonds + retirement accounts  -> bank + FDs + equity + MFs + retirement + bonds
                   (cash in hand, gold, property and crypto are not financial assets in FIN)
      saved        SCF SAVED = spending below income over the PAST YEAR                -> last 12 months' income minus spending > 0
    Known differences that cannot be removed with Finora's data (documented, shown in the comparison note):
      income       SCF INCOME is gross pre-tax income; Finora sees take-home credits, so Finora ratios to income run higher.
      card balance SCF CCBAL is the balance still owed after the last payment; Finora uses the current outstanding balance."""
    from ..services import calculations as C
    inc_m = float(monthly["income"].mean()) if len(monthly) else 0.0
    if inc_m <= 0:
        return None
    annual = inc_m * 12
    nw = C.net_worth(ident)
    b = nw["breakdown"]
    liquid = b.get("Bank balances", 0)
    bonds = sum(o["value"] for o in ident.other_assets if o["kind"] == "bonds")
    fin = (b.get("Bank balances", 0) + b.get("Fixed deposits", 0) + b.get("Equity", 0) + b.get("Mutual funds", 0)
           + b.get("Retirement (EPF/PPF/NPS)", 0) + bonds)
    debt = nw["total_liabilities"] or 0.0
    payments = sum(l["emi"] for l in ident.loans) + sum(max(c["min_due"], 0) for c in ident.cards)
    equity = b.get("Equity", 0) + sum(f["units"] * f["current_nav"] for f in ident.mfs if f["fund_type"] != "debt")
    last12 = monthly.sort_values("month").tail(12)
    return {"liquid_months": liquid / inc_m, "debt_to_income": debt / annual, "payment_to_income": payments * 12 / annual,
            "card_to_income": sum(c["outstanding"] for c in ident.cards) / annual,
            "networth_to_income": (nw["net_worth"] or 0.0) / annual,
            "financial_share": fin / nw["total_assets"] if nw["total_assets"] else 0.0,
            "equity_share": min(1.0, equity / fin) if fin else 0.0,
            "saved_last_year": 1.0 if float(last12["savings"].sum()) > 0 else 0.0}


def _analyse_scf(art: dict, ident, monthly: pd.DataFrame) -> dict:
    from .real.peers import transform, weighted_quantile, CLIP
    feats = scf_profile_features(ident, monthly)
    if feats is None:
        return {"available": False, "note": "Peer comparison needs your income to compute the ratios."}
    x = transform(pd.DataFrame([feats]))
    k = int(art["kmeans"].predict(art["scaler"].transform(x))[0])
    ref = art["reference"]
    w_all = ref["w"].to_numpy()
    grp = ref[ref["cluster"] == k]
    comp, strengths, weaknesses = [], [], []
    for f in art["features"]:
        lo, hi = CLIP[f]
        you = float(np.clip(feats[f], lo, hi))
        below = float(w_all[(ref[f] < you).to_numpy()].sum() / w_all.sum() * 100)
        better = below if art["higher_is_better"][f] else 100 - below
        comp.append({"metric": art["labels"][f], "you": round(you, 3),
                     "peer_group_median": round(weighted_quantile(grp[f].to_numpy(), grp["w"].to_numpy(), 0.5), 3),
                     "everyone_median": round(weighted_quantile(ref[f].to_numpy(), w_all, 0.5), 3),
                     "better_than_pct_of_people": round(better)})
        if better >= 70:
            strengths.append(art["labels"][f])
        elif better <= 30:
            weaknesses.append(art["labels"][f])
    # sizes are survey-WEIGHTED households (the 5 implicates of a family share one family's weight), never record counts
    return {"peer_group": art["names"][k], "peer_group_share_pct": round(float(grp["w"].sum() / w_all.sum() * 100), 1),
            "peer_group_households_millions": round(float(grp["w"].sum()) / 1e6, 1),
            "population_households_millions": round(float(w_all.sum()) / 1e6, 1),
            "comparison": comp, "strengths": strengths, "weaknesses": weaknesses, "units": "ratios (not percentages)",
            "all_groups": [{"name": g["name"], "share_pct": g["weighted_share_pct"]} for g in art["groups"]],
            "note": "Compared with US households in the Federal Reserve's Survey of Consumer Finances 2022 (real survey data, "
                    "weighted). These are US household benchmarks, not Indian individual ones; a Finora profile may be one person. "
                    "The survey uses gross (pre-tax) income while Finora sees take-home pay, so your ratios to income read "
                    "somewhat higher than a US household's would; card balance is your current outstanding amount."}

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

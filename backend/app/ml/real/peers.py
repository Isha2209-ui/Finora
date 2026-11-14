"""Stage 1 peer benchmarking: K-Means (unchanged algorithm) on the Federal Reserve Survey of Consumer Finances 2022.

US HOUSEHOLD peer groups. Not representative of Indian households (Stage 2: AIDIS 2019).

Features are ratios a Finora profile can also compute (so groups compare like with like, whatever the currency):
  liquid_months       LIQ / (INCOME / 12)                 months of income held in liquid accounts
  debt_to_income      DEBT2INC = DEBT / INCOME
  payment_to_income   PIRTOTAL = debt payments / income
  card_to_income      CCBAL / INCOME
  networth_to_income  NETWORTH / INCOME
  financial_share     FIN / ASSET                         financial assets as a share of all assets
  equity_share        EQUITY / FIN                        shares and equity funds as a share of financial assets
  saved_last_year     SAVED (spending was less than income over the past year)
TOTSPENDNH (spending) is not populated in the 2022 extract (0 for every record), so spending ratios are not used.

Multiple imputation: SCF stores 5 implicates per family (records Y1 = 10*YY1 + 1..5). For a descriptive clustering the
implicates are STACKED with survey weight WGT (each implicate's WGT sums to 1/5 of the population in the public extract), so each family contributes its full weight once, integrated over imputation
uncertainty (the standard way to use all implicates for a point analysis; Rubin's rules are for estimator variances).
Stability: K-Means is also fitted on each implicate separately and agreement is measured with the adjusted Rand index (ARI)
on the same families, plus silhouette and Davies-Bouldin per implicate.
"""
from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from ..provenance import Run, sha256, source_record
from ...config import DATASETS_DIR

RAW = DATASETS_DIR / "raw" / "scf2022" / "scfp2022excel.zip"
FEATURES = ["liquid_months", "debt_to_income", "payment_to_income", "card_to_income", "networth_to_income", "financial_share",
            "equity_share", "saved_last_year"]
LABELS = {"liquid_months": "Liquid savings (months of income)", "debt_to_income": "Debt / yearly income",
          "payment_to_income": "Debt payments / income", "card_to_income": "Card balance / yearly income",
          "networth_to_income": "Net worth / yearly income", "financial_share": "Financial assets / all assets",
          "equity_share": "Equity / financial assets", "saved_last_year": "Saved last year"}
HIGHER_IS_BETTER = {"liquid_months": True, "debt_to_income": False, "payment_to_income": False, "card_to_income": False,
                    "networth_to_income": True, "financial_share": True, "equity_share": True, "saved_last_year": True}
CLIP = {"liquid_months": (0, 60), "debt_to_income": (0, 10), "payment_to_income": (0, 1.5), "card_to_income": (0, 1),
        "networth_to_income": (-5, 50), "financial_share": (0, 1), "equity_share": (0, 1), "saved_last_year": (0, 1)}
LOGGED = {"liquid_months", "debt_to_income", "networth_to_income"}


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Clip extreme ratios and compress heavy tails (signed log) - same transform for SCF and for a Finora profile."""
    x = df[FEATURES].astype(float).copy()
    for f, (lo, hi) in CLIP.items():
        x[f] = x[f].clip(lo, hi)
    for f in LOGGED:
        x[f] = np.sign(x[f]) * np.log1p(np.abs(x[f]))
    return x


def load() -> tuple[pd.DataFrame, dict]:
    with zipfile.ZipFile(RAW) as z:
        d = pd.read_csv(z.open("SCFP2022.csv"), usecols=["YY1", "Y1", "WGT", "INCOME", "LIQ", "FIN", "ASSET", "DEBT", "NETWORTH",
                                                          "DEBT2INC", "PIRTOTAL", "CCBAL", "EQUITY", "SAVED", "AGE", "TOTSPENDNH"])
    rep = {"records": int(len(d)), "families": int(d["YY1"].nunique()), "implicates_per_family": int(d.groupby("YY1").size().mode()[0]),
           "totspendnh_nonzero_records": int((d["TOTSPENDNH"] != 0).sum())}
    d["implicate"] = d["Y1"] - 10 * d["YY1"]
    keep = d["INCOME"] > 0
    rep["records_without_positive_income_excluded"] = int((~keep).sum())
    d = d[keep].copy()
    inc = d["INCOME"]
    d["liquid_months"] = d["LIQ"] / (inc / 12)
    d["debt_to_income"] = d["DEBT2INC"]
    d["payment_to_income"] = d["PIRTOTAL"]
    d["card_to_income"] = d["CCBAL"] / inc
    d["networth_to_income"] = d["NETWORTH"] / inc
    d["financial_share"] = np.where(d["ASSET"] > 0, d["FIN"] / d["ASSET"].where(d["ASSET"] > 0), 0.0)
    d["equity_share"] = np.where(d["FIN"] > 0, d["EQUITY"] / d["FIN"].where(d["FIN"] > 0), 0.0)
    d["saved_last_year"] = d["SAVED"].astype(float)
    # In the public summary extract each implicate's WGT already sums to 1/5 of the population (26.3 M of ~131 M families),
    # so stacking the 5 implicates with WGT itself gives each family its full weight once (stacked total ~131 M).
    d["w"] = d["WGT"]
    rep["records_used"] = int(len(d))
    return d, rep


def _name(md: dict) -> str:
    """Name a group from its WEIGHTED MEDIANS in natural units (what the user sees); documented thresholds, no hard-coded ids."""
    if md["debt_to_income"] >= 1.5 and md["networth_to_income"] >= 1:
        return "Borrowing to own (large loans, positive net worth)"
    if md["debt_to_income"] >= 1.5 or md["payment_to_income"] >= 0.3:
        return "Heavily indebted"
    if md["card_to_income"] >= 0.1:
        return "Card-balance reliant"
    if md["networth_to_income"] >= 4 and md["financial_share"] >= 0.3:
        return "Wealthy investors"
    if md["liquid_months"] < 1 and md["saved_last_year"] < 0.5:
        return "Thin cushion, not saving"
    if md["saved_last_year"] >= 0.5 and md["liquid_months"] >= 3:
        return "Steady savers"
    return "Middle of the road"


def weighted_quantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][np.searchsorted(cw, q * cw[-1])])


def train(approved: bool, seed: int = 7) -> tuple[str, dict]:
    run = Run("peers", "python -m app.ml.train peers")
    d, rep = load()
    X = transform(d)
    scaler = StandardScaler().fit(X, sample_weight=d["w"])
    Z = scaler.transform(X)
    one = (d["implicate"] == 1).to_numpy()
    scan = []
    for k in range(3, 8):
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Z, sample_weight=d["w"])
        lab = km.predict(Z[one])
        scan.append({"k": k, "silhouette_implicate1": round(float(silhouette_score(Z[one], lab, sample_size=4000, random_state=seed)), 4),
                     "davies_bouldin_implicate1": round(float(davies_bouldin_score(Z[one], lab)), 4)})
    best_k = max(scan, key=lambda s: s["silhouette_implicate1"])["k"]
    km = KMeans(n_clusters=best_k, n_init=20, random_state=seed).fit(Z, sample_weight=d["w"])
    d["cluster"] = km.predict(Z)
    # stability across implicates: per-implicate models vs the stacked model on the same families
    per_imp, labels_by_imp = [], {}
    for i in range(1, 6):
        m = (d["implicate"] == i).to_numpy()
        ki = KMeans(n_clusters=best_k, n_init=10, random_state=seed).fit(Z[m], sample_weight=d["w"][m])
        li = ki.predict(Z[m])
        fam = d.loc[m, "YY1"].to_numpy()
        labels_by_imp[i] = pd.Series(d.loc[m, "cluster"].to_numpy(), index=fam)
        per_imp.append({"implicate": i, "families": int(m.sum()),
                        "ari_vs_stacked_model": round(float(adjusted_rand_score(d.loc[m, "cluster"], li)), 4),
                        "silhouette": round(float(silhouette_score(Z[m], d.loc[m, "cluster"], sample_size=4000, random_state=seed)), 4),
                        "davies_bouldin": round(float(davies_bouldin_score(Z[m], d.loc[m, "cluster"])), 4)})
    cross = []
    for a in range(1, 6):
        for b in range(a + 1, 6):
            common = labels_by_imp[a].index.intersection(labels_by_imp[b].index)
            cross.append(adjusted_rand_score(labels_by_imp[a].loc[common], labels_by_imp[b].loc[common]))
    # reference distributions for comparisons (weighted, on the original ratio scale after clipping)
    raw = d[FEATURES].astype(float).copy()
    for f, (lo, hi) in CLIP.items():
        raw[f] = raw[f].clip(lo, hi)
    w = d["w"].to_numpy()
    groups, names, used = [], {}, set()
    for c in range(best_k):
        m = (d["cluster"] == c).to_numpy()
        md = {f: round(weighted_quantile(raw[f].to_numpy()[m], w[m], 0.5), 3) for f in FEATURES}
        n = _name(md)
        names[c] = n if n not in used else f"{n} ({c + 1})"
        used.add(names[c])
        groups.append({"id": c, "name": names[c], "weighted_share_pct": round(float(w[m].sum() / w.sum() * 100), 1),
                       "families": int(d.loc[m, "YY1"].nunique()), "median": md})
    fam_groups = d.groupby("YY1")["cluster"].nunique()
    fam_w = d.groupby("YY1")["w"].sum()
    verification = {
        "families": int(d["YY1"].nunique()), "records_used": int(len(d)),
        "every_family_has_5_implicates_in_source": bool(rep["implicates_per_family"] == 5),
        "stacked_weight_total_millions": round(float(d["w"].sum()) / 1e6, 2),
        "weight_note": "Each implicate's WGT sums to ~26.3 M (1/5 of ~131 M US families); stacked with WGT the total is the population once, "
                       "so no household is counted more than once.",
        "families_in_one_group_across_all_their_implicates_pct": round(float((fam_groups == 1).mean() * 100), 1),
        "same_weighted_pct": round(float(fam_w[fam_groups == 1].sum() / fam_w.sum() * 100), 1),
        "excluded_non_positive_income_records": rep["records_without_positive_income_excluded"],
        "values_clipped_pct": {f: round(float(((d[f] < lo) | (d[f] > hi)).mean() * 100), 2) for f, (lo, hi) in CLIP.items()},
        "zero_values_pct": {f: round(float((d[f] == 0).mean() * 100), 1) for f in FEATURES},
        "zero_and_missing_handling": "No missing values in the extract (imputed by the Federal Reserve). Income <= 0: record excluded. "
                                     "Assets <= 0: financial share 0. Financial assets <= 0: equity share 0. Ratios are clipped to the "
                                     "ranges in CLIP and three heavy-tailed ratios are signed-log transformed, identically for Finora profiles.",
    }
    metrics = {
        "verification": verification,
        "task": "Group households by financial position; compare a Finora profile with similar US households",
        "unit": "household (SCF 'family')", "k_scan": scan, "chosen_k": best_k, "chosen_by": "highest silhouette (implicate 1)",
        "stability": {"per_implicate": per_imp, "cross_implicate_ari_mean": round(float(np.mean(cross)), 4),
                      "cross_implicate_ari_min": round(float(np.min(cross)), 4)},
        "groups": groups, "features": [LABELS[f] for f in FEATURES], "data": rep,
    }
    src = source_record("scf2022")
    files = {f["file"]: f for f in src.get("files", [])}
    stable = float(np.mean(cross)) >= 0.7
    prov = {
        "data_status": "real", "evaluation_passed": bool(np.min(cross) >= 0.7), "approved_by_owner": bool(approved),
        "evaluation_note": f"Cluster agreement across the 5 implicates: mean ARI {np.mean(cross):.2f} ({'stable' if stable else 'only moderately stable'}).",
        "deployment_label": "US household peer groups (Federal Reserve SCF 2022); not Indian benchmarks",
        "scope": "US households", "datasets": [{
            "key": "scf2022", "name": "Survey of Consumer Finances 2022, summary extract", "publisher": "Board of Governors of the Federal Reserve System",
            "source_url": "https://www.federalreserve.gov/econres/scf_2022.htm", "download_url": files.get("scfp2022excel.zip", {}).get("url"),
            "collection_period": "Survey year 2022 (income refers to 2021)", "geography": "United States",
            "population": "US families (household-level), with survey weights", "records": rep["records"], "families": rep["families"],
            "features": 362, "format": "CSV in zip", "target": "none (unsupervised clustering)", "observations": "real survey responses; "
            "missing answers are multiply imputed by the Federal Reserve (5 implicates)", "synthetic_observations": "none (imputation of item "
            "non-response by the publisher is disclosed, not synthetic people)", "licence": src.get("licence"),
            "file_sha256": files.get("scfp2022excel.zip", {}).get("sha256"), "codebook_sha256": files.get("codebk2022.txt", {}).get("sha256"),
            "downloaded": src.get("downloaded_at"), "cleaning": rep,
            "preprocessing": "8 ratio features (see module docstring), clipped and signed-log compressed, standardised with survey weights.",
            "missing_values": "none after the publisher's imputation; families with income <= 0 excluded (counted)",
            "known_biases": "US households, 2022 dollars; wealthy households oversampled by design (weights correct for this)."}],
        "methodology": "Weighted K-Means on stacked implicates (weight WGT; per-implicate WGT sums to 1/5 of the population); k by silhouette; stability by ARI across implicates.",
        "limitations": "US households, not Indian; household-level, while a Finora profile may be one person; spending is not in the 2022 "
                       "summary extract, so groups are about savings, debt and assets rather than spending habits.",
        "reproducible": "python -m app.ml.train peers (seed 7) with the raw file above",
    }
    art = {"kind": "scf_households", "kmeans": km, "scaler": scaler, "names": names, "features": FEATURES, "labels": LABELS,
           "higher_is_better": HIGHER_IS_BETTER, "reference": raw.assign(cluster=d["cluster"].to_numpy(), w=w).reset_index(drop=True),
           "groups": groups}
    out = run.save(art, metrics, prov)
    return run.version, {"out": str(out), "scan": scan, "k": best_k, "stability": metrics["stability"], "groups": groups}

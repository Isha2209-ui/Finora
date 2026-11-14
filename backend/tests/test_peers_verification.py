"""Peer benchmarking (SCF 2022) verification: households not records, survey weights, population, cluster sizes, weighted
percentiles, stability across the 5 implicates, the 8 Finora profile features and the cluster descriptions."""
import joblib
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app import models as M
from app.database import SessionLocal
from app.ml import peers as PE, provenance as PV, registry
from app.ml.real import peers as P
from app.services import calculations as C
from app.services.loader import load_identity

pytestmark = pytest.mark.skipif(not P.RAW.exists(), reason="SCF 2022 raw file not downloaded (python -m app.ml.data.acquire scf2022)")


@pytest.fixture(scope="module")
def scf():
    d, rep = P.load()
    return d, rep


@pytest.fixture(scope="module")
def art():
    return registry.get("peers")


def test_households_are_counted_once_with_the_survey_weights(scf):
    d, rep = scf
    assert rep["implicates_per_family"] == 5 and d.groupby("YY1")["implicate"].nunique().max() == 5
    per_imp = d.groupby("implicate")["WGT"].sum() / 1e6
    assert per_imp.max() - per_imp.min() < 0.5                       # each implicate represents the same population
    total = d["w"].sum() / 1e6
    assert 125 < total < 135                                          # ~131 M US families, counted ONCE (not 5x, not 1/5)
    assert abs(total - per_imp.sum()) < 0.01                          # stacked weight = sum of the five implicate weights


def test_cluster_sizes_are_weighted_household_shares(scf, art):
    d, _ = scf
    lab = art["kmeans"].predict(art["scaler"].transform(P.transform(d)))
    for g in art["groups"]:
        share = d["w"][lab == g["id"]].sum() / d["w"].sum() * 100
        assert abs(share - g["weighted_share_pct"]) < 0.05
        assert g["families"] <= d["YY1"].nunique()                     # a household count, never a record count
    assert abs(sum(g["weighted_share_pct"] for g in art["groups"]) - 100) < 0.2


def test_membership_is_stable_across_implicates(scf, art):
    d, _ = scf
    d = d.assign(c=art["kmeans"].predict(art["scaler"].transform(P.transform(d))))
    same = (d.groupby("YY1")["c"].nunique() == 1).mean()
    assert same >= 0.85                                               # measured 91.6%
    m = registry.metrics()["peers"]["stability"]
    assert m["cross_implicate_ari_min"] >= 0.7


def test_weighted_quantile_is_correct():
    x, w = np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 1.0, 1.0, 5.0])
    assert P.weighted_quantile(x, w, 0.5) == 4.0                      # 5/8 of the weight sits on 4
    assert P.weighted_quantile(x, np.ones(4), 0.5) == 2.0


def test_cluster_descriptions_match_their_weighted_medians(art):
    for g in art["groups"]:
        assert P._name(g["median"]).split(" (")[0] == g["name"].split(" (")[0]
    names = {g["name"] for g in art["groups"]}
    borrowing = next(g for g in art["groups"] if g["name"].startswith("Borrowing to own"))
    assert borrowing["median"]["debt_to_income"] >= 1.5 and borrowing["median"]["networth_to_income"] >= 1
    assert len(names) == len(art["groups"])


def _ident(iid):
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == iid))
        ident = load_identity(db, uid)
    monthly, _, _ = C.monthly_frame(ident)
    return ident, monthly


@pytest.mark.parametrize("iid", ["FINORA_USER_001", "FINORA_USER_002"])
def test_the_eight_finora_features_follow_the_scf_definitions(iid):
    ident, monthly = _ident(iid)
    f = PE.scf_profile_features(ident, monthly)
    assert set(f) == set(P.FEATURES) and all(np.isfinite(v) for v in f.values())
    inc_m = monthly["income"].mean()
    nw = C.net_worth(ident)
    b = nw["breakdown"]
    assert f["liquid_months"] == pytest.approx(b.get("Bank balances", 0) / inc_m)              # SCF LIQ: no FDs, no cash
    bonds = sum(o["value"] for o in ident.other_assets if o["kind"] == "bonds")
    fin = sum(b.get(k, 0) for k in ("Bank balances", "Fixed deposits", "Equity", "Mutual funds", "Retirement (EPF/PPF/NPS)")) + bonds
    assert f["financial_share"] == pytest.approx(fin / nw["total_assets"])                     # SCF FIN: no gold/cash/property
    assert f["debt_to_income"] == pytest.approx(nw["total_liabilities"] / (inc_m * 12))
    last12 = monthly.sort_values("month").tail(12)
    assert f["saved_last_year"] == (1.0 if last12["savings"].sum() > 0 else 0.0)                # past year only
    assert 0 <= f["equity_share"] <= 1


def test_profile_percentiles_are_weighted_over_households(art):
    ident, monthly = _ident("FINORA_USER_002")
    out = PE._analyse_scf(art, ident, monthly)
    ref, f = art["reference"], PE.scf_profile_features(ident, monthly)
    w = ref["w"].to_numpy()
    lo, hi = P.CLIP["liquid_months"]
    you = float(np.clip(f["liquid_months"], lo, hi))
    expected = w[(ref["liquid_months"] < you).to_numpy()].sum() / w.sum() * 100
    row = next(c for c in out["comparison"] if c["metric"] == art["labels"]["liquid_months"])
    assert row["better_than_pct_of_people"] == round(expected)
    assert 125 < out["population_households_millions"] < 135
    grp = next(g for g in art["groups"] if g["name"] == out["peer_group"])
    assert out["peer_group_share_pct"] == pytest.approx(grp["weighted_share_pct"], abs=0.1)
    assert "peer_group_size" not in out and "US households" in out["note"] and "take-home" in out["note"]

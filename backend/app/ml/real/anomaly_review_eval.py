"""Offline evaluation of the deployed anomaly model against the BLINDED human review (Phase 6, part B).
Run only after reviewers have labelled the sample:  python -m app.ml.real.anomaly_review_eval

What a label means: a person judged the transaction unusual FOR THAT CARDHOLDER ("somewhat" or "very" unusual). It is
perceived unusualness, not confirmed fraud, and the results must be described that way.

Estimation: the sample is stratified (S1 model-flagged, S2 rule-flagged only, S3 neither) with known selection probabilities,
so population quantities are Horvitz-Thompson estimates: each labelled item stands for 1/p items of its stratum.
- precision of the model flag  = share judged unusual within S1 (S1 is the flagged population, sampled uniformly)
- recall of the model flag     = N_S1*p_S1 / sum_h N_h*p_h  (estimated, with a stratified bootstrap 95% interval)
Recall is reported as VALID only if every stratum has at least MIN_PER_STRATUM consensus labels and at least one item judged
unusual outside S1; otherwise it is reported as "not estimable from this sample" rather than a number.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
from sqlalchemy import select

from ... import models as M
from ...database import SessionLocal

UNUSUAL = {"somewhat_unusual", "very_unusual"}
MIN_PER_STRATUM = 30


def consensus(labels: list[str]) -> str | None:
    """Majority of the reviewers who could judge (cannot_tell ignored); ties -> None (excluded and counted)."""
    votes = [("unusual" if x in UNUSUAL else "usual") for x in labels if x != "cannot_tell"]
    if not votes:
        return None
    c = Counter(votes).most_common()
    return None if len(c) > 1 and c[0][1] == c[1][1] else c[0][0]


def evaluate(sample: dict, labels: dict[str, list[str]], seed: int = 7, boots: int = 2000) -> dict:
    design = sample["design"]
    by = {s: [] for s in design}
    excluded = 0
    for it in sample["items"]:
        c = consensus(labels.get(it["item_id"], []))
        if c is None:
            excluded += 1
            continue
        by[it["stratum"]].append(c == "unusual")
    p = {s: (float(np.mean(v)) if v else None) for s, v in by.items()}
    N = {s: design[s]["population"] for s in design}

    def recall(pp):
        tot = sum(N[s] * pp[s] for s in pp)
        return None if not tot else N["S1_model_flagged"] * pp["S1_model_flagged"] / tot

    valid = all(len(by[s]) >= MIN_PER_STRATUM for s in by) and any(any(by[s]) for s in by if s != "S1_model_flagged")
    out = {"labelled_items_with_consensus": sum(len(v) for v in by.values()), "excluded_no_consensus": excluded,
           "per_stratum": {s: {"consensus_labels": len(by[s]), "judged_unusual_share": None if p[s] is None else round(p[s], 3),
                               "population": N[s]} for s in by},
           "model_precision_perceived_unusual": None if p["S1_model_flagged"] is None else round(p["S1_model_flagged"], 3),
           "share_of_flags_judged_usual": None if p["S1_model_flagged"] is None else round(1 - p["S1_model_flagged"], 3),
           "label_meaning": "perceived unusualness for the cardholder, judged by people; NOT confirmed fraud"}
    if valid:
        rng = np.random.default_rng(seed)
        bs = []
        for _ in range(boots):
            pp = {s: float(np.mean(rng.choice(by[s], size=len(by[s])))) for s in by}
            r = recall(pp)
            if r is not None:
                bs.append(r)
        out["model_recall_perceived_unusual"] = {"estimate": round(recall(p), 3), "ci95": [round(float(np.percentile(bs, 2.5)), 3),
                                                                                         round(float(np.percentile(bs, 97.5)), 3)]}
        usual_tot = sum(N[s] * (1 - p[s]) for s in p)
        out["false_positive_rate_estimate"] = round(N["S1_model_flagged"] * (1 - p["S1_model_flagged"]) / usual_tot, 4) if usual_tot else None
    else:
        out["false_positive_rate_estimate"] = "not estimable from this sample"
        out["model_recall_perceived_unusual"] = "not estimable from this sample (too few consensus labels per stratum, or no " \
                                                "unusual items found outside the flagged stratum)"
    return out


def main():
    from ...routes.review import sample_path
    p = sample_path()
    if p is None:
        raise SystemExit("no review sample")
    sample = json.loads(p.read_text())
    db = SessionLocal()
    try:
        rows = db.scalars(select(M.AnomalyReviewLabel).where(M.AnomalyReviewLabel.sample_version == sample["version"])).all()
    finally:
        db.close()
    labels: dict[str, list[str]] = {}
    for r in rows:
        labels.setdefault(r.item_id, []).append(r.label)
    if not labels:
        raise SystemExit("No human labels yet. Nothing is estimated until people have reviewed the sample.")
    from datetime import datetime, timezone
    result = {**evaluate(sample, labels), "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "sample_version": sample["version"], "reviewers": len({r.reviewer_id for r in rows}), "labels": len(rows)}
    (p.parent / "review_result.json").write_text(json.dumps(result, indent=2))     # read by acceptance via load_metrics
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

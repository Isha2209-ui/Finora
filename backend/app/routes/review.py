"""Blinded human review of the anomaly model (Phase 6, part B).

    GET  /api/models/anomaly-review            the sample as reviewers see it + this reviewer's own labels
    PUT  /api/models/anomaly-review/{item_id}  save / change this reviewer's label for one item
    GET  /api/models/anomaly-review/progress   label counts and inter-reviewer agreement (no model output)

Blinding: items are served WITHOUT the model score, the flag, the sampling stratum or the selection probability, in a
random order fixed when the sample was drawn. Those fields stay in the sample file and are used only by the offline
evaluation (app/ml/real/anomaly_review_eval.py) once labelling is finished. Nothing here assigns a label automatically.
"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import Current, audit, current_account
from ..database import get_db
from ..ml import provenance as PV

router = APIRouter(prefix="/api/models/anomaly-review", tags=["Model review"])
LABELS = ["usual", "somewhat_unusual", "very_unusual", "cannot_tell"]


def sample_path():
    """The review sample of the ACTIVE anomaly version (else the latest trained one), stored next to that model."""
    act = PV.active().get("anomaly")
    if act:
        p = PV.REAL_DIR / "anomaly" / act["version"] / "review_sample.json"
        if p.exists():
            return p
    files = sorted((PV.REAL_DIR / "anomaly").glob("*/review_sample.json"))
    return files[-1] if files else None


def _sample() -> dict:
    p = sample_path()
    if p is None:
        raise HTTPException(404, "No review sample yet: the anomaly model has not been trained on real data.")
    return json.loads(p.read_text())


def _reviewer(cur: Current) -> M.AppUser:
    if cur.user.is_guest:
        raise HTTPException(403, "Guest sessions cannot review. Sign in with a full account.")
    return cur.user


class LabelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal["usual", "somewhat_unusual", "very_unusual", "cannot_tell"]
    note: str = Field(default="", max_length=500)


@router.get("", summary="The blinded review sample and your labels")
def get_sample(cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    me = _reviewer(cur)
    s = _sample()
    mine = {r.item_id: {"label": r.label, "note": r.note} for r in db.scalars(
        select(M.AnomalyReviewLabel).where(M.AnomalyReviewLabel.sample_version == s["version"],
                                           M.AnomalyReviewLabel.reviewer_id == me.id))}
    items = [{"item_id": it["item_id"], **it["shown"], "your_label": mine.get(it["item_id"])} for it in s["items"]]
    return {"sample_version": s["version"], "labels": LABELS, "items": items, "done": len(mine), "total": len(items),
            "instructions": "For each transaction, judge how unusual it looks FOR THIS CARDHOLDER, given their own history in "
                            "that category. This is not a fraud judgement. Use 'cannot tell' when the information is not enough."}


@router.put("/{item_id}", summary="Save your label for one item")
def put_label(item_id: str, body: LabelIn, request: Request, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    me = _reviewer(cur)
    s = _sample()
    if item_id not in {it["item_id"] for it in s["items"]}:
        raise HTTPException(404, "Unknown item.")
    row = db.scalar(select(M.AnomalyReviewLabel).where(M.AnomalyReviewLabel.sample_version == s["version"],
                                                       M.AnomalyReviewLabel.item_id == item_id,
                                                       M.AnomalyReviewLabel.reviewer_id == me.id))
    if row is None:
        row = M.AnomalyReviewLabel(sample_version=s["version"], item_id=item_id, reviewer_id=me.id)
        db.add(row)
    row.label, row.note = body.label, body.note.strip()
    audit(db, "anomaly_review.label", request=request, app_user_id=me.id, detail={"item": item_id}, commit=False)
    db.commit()
    return {"item_id": item_id, "label": row.label}


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


@router.get("/progress", summary="Labelling progress and agreement between reviewers")
def progress(cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    _reviewer(cur)
    s = _sample()
    rows = db.scalars(select(M.AnomalyReviewLabel).where(M.AnomalyReviewLabel.sample_version == s["version"])).all()
    by_rev: dict[int, dict[str, str]] = {}
    for r in rows:
        by_rev.setdefault(r.reviewer_id, {})[r.item_id] = r.label
    revs = sorted(by_rev)
    pairs = []
    for i, a in enumerate(revs):
        for b in revs[i + 1:]:
            common = sorted(set(by_rev[a]) & set(by_rev[b]))
            pairs.append({"reviewers": [a, b], "items_in_common": len(common),
                          "cohen_kappa": cohen_kappa([by_rev[a][k] for k in common], [by_rev[b][k] for k in common])})
    return {"sample_version": s["version"], "total_items": len(s["items"]), "reviewers": len(revs),
            "labels_per_reviewer": {str(r): len(by_rev[r]) for r in revs},
            "items_with_two_or_more_labels": sum(1 for it in s["items"] if sum(it["item_id"] in by_rev[r] for r in revs) >= 2),
            "agreement": pairs,
            "note": "Agreement between people only. Model results are not shown here; they are computed offline after review."}

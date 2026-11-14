"""The four demo identities must produce exactly the same numbers as before Phase 3.

Phase 6 (real-data models) changes the ML outputs BY DESIGN: credit risk and peers come from new real-data models, and the
forecast and anomaly models are not active. So the check is split, without loosening anything that did not change:
  1. every non-ML value (cash flow, net worth, FIRE, tax, health score, ...) must still be exactly the golden value;
  2. the recommendation and alert ENGINE is unchanged: fed the golden (pre-Phase-6) ML outputs it must reproduce the golden
     recommendations and alerts exactly, so any difference in them comes only from the new ML outputs.

tests/golden/demo_analysis_before_phase3.json was captured from master before any Phase 3 change. Phase 3 only
ADDS fields (availability flags, coverage, completeness); every pre-existing value must be unchanged, except the
explanatory texts listed below, whose wording was updated on purpose.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as M
from app.database import SessionLocal
from app.services import analysis

from .conftest import DEMO

GOLDEN = json.loads((Path(__file__).parent / "golden" / "demo_analysis_before_phase3.json").read_text())
REWORDED = {".health_score.method", ".tax.note"}


def _flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _flat(v, f"{p}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _flat(v, f"{p}[{i}]")
    else:
        yield p, o


ML_DERIVED = (".ml.", ".ml_errors", ".recommendations", ".alerts")


@pytest.mark.parametrize("iid", list(DEMO.values()))
def test_demo_analysis_unchanged(iid):
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == iid))
        now = json.loads(json.dumps(analysis.run(db, uid, save=False), default=str))
    now.pop("generated_at", None)
    for v in now["ml"].values():
        if isinstance(v, dict):
            v.pop("scores", None)
    before, after = dict(_flat(GOLDEN[iid])), dict(_flat(now))
    calc = [k for k in before if not k.startswith(ML_DERIVED)]
    missing = [k for k in calc if k not in after]
    changed = [(k, before[k], after[k]) for k in calc if k in after and before[k] != after[k] and k not in REWORDED]
    assert not missing, missing[:10]
    assert not changed, changed[:10]
    assert len(calc) > 700                         # the exact comparison still covers the whole calculation engine


@pytest.mark.parametrize("iid", list(DEMO.values()))
def test_recommendation_engine_reproduces_golden_output_from_golden_ml(iid):
    from app.services import recommendations as R
    from app.services.analysis import clean_json
    from app.services.loader import load_identity
    from app.services.snapshot import build
    g = GOLDEN[iid]
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == iid))
        snap = build(load_identity(db, uid), None)
    recs = R.build(snap, g["ml"])
    out = json.loads(json.dumps(clean_json({"recommendations": recs, "alerts": R.alerts(snap, g["ml"], recs)}), default=str))
    assert out == {"recommendations": g["recommendations"], "alerts": g["alerts"]}
    assert len(g["recommendations"]) >= 3

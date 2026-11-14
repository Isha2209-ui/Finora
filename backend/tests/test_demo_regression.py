"""The four demo identities must produce exactly the same numbers as before Phase 3.

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
    missing = [k for k in before if k not in after]
    changed = [(k, before[k], after[k]) for k in before if k in after and before[k] != after[k] and k not in REWORDED]
    assert not missing, missing[:10]
    assert not changed, changed[:10]
    assert len(before) > 1000                      # the comparison really covers the whole analysis

"""Train Finora's models on the approved REAL datasets, locally, with full provenance.

Usage:
  python -m app.ml.train [credit_risk categoriser anomaly anomaly_ulb forecast peers] [--approved]
  python -m app.ml.train activate <model> <version> --reason "why" [--experimental]
  python -m app.ml.train deactivate|rollback <model> --reason "why"
  python -m app.ml.train check            (acceptance criteria of every trained version)
  python -m app.ml.train status

Each run writes artifacts/real/<model>/<version>/{model.joblib, metrics.json, provenance.json}. Nothing is loaded by the
app until a version is activated (artifacts/active.json), and activation refuses anything that is not real-data, evaluated
and approved. `--approved` records that the owner approved this dataset + method (Phase 6 approval, 2026-11-14).
There is no synthetic training path here; the legacy synthetic artifacts are kept, read-only, in
artifacts/legacy-synthetic-2026-11-13/ for rollback (MODEL_SET=legacy-synthetic).
"""
from __future__ import annotations

import json
import sys

from . import provenance as PV

TRAINERS = ["credit_risk", "categoriser", "anomaly", "anomaly_ulb", "forecast", "peers"]


def _trainer(name: str):
    from .real import anomaly, anomaly_ulb, categoriser, credit, forecast, peers
    return {"credit_risk": credit.train, "categoriser": categoriser.train, "anomaly": anomaly.train,
            "anomaly_ulb": anomaly_ulb.train, "forecast": forecast.train, "peers": peers.train}[name]


def main(argv: list[str]) -> int:
    if argv[:1] == ["status"]:
        print(json.dumps(PV.active(), indent=2))
        return 0
    if argv[:1] in (["deactivate"], ["rollback"]):
        if len(argv) < 2 or "--reason" not in argv:
            print(f"usage: python -m app.ml.train {argv[0]} <model> --reason \"why\"")
            return 2
        fn = PV.deactivate if argv[0] == "deactivate" else PV.rollback
        print(json.dumps(fn(argv[1], argv[argv.index("--reason") + 1]), indent=2))
        return 0
    if argv[:1] == ["check"]:
        from . import acceptance
        for d in sorted(PV.REAL_DIR.glob("*/*/metrics.json")):
            ok, checks = acceptance.check(d.parent.parent.name, PV.load_metrics(d.parent))
            print(f"{d.parent.parent.name:<22} {d.parent.name}  {'PASS' if ok else 'FAIL'}")
            for c in checks:
                print(f"    {'ok  ' if c['passed'] else 'FAIL'} {c['criterion']}: {c['value']}")
        return 0
    if argv[:1] == ["activate"]:
        if len(argv) < 3 or "--reason" not in argv:
            print("usage: python -m app.ml.train activate <model> <version> --reason \"why\"")
            return 2
        reason = argv[argv.index("--reason") + 1]
        print(json.dumps(PV.activate(argv[1], argv[2], reason, experimental="--experimental" in argv), indent=2))
        return 0
    approved = "--approved" in argv
    names = [a for a in argv if not a.startswith("--")] or TRAINERS
    unknown = [n for n in names if n not in TRAINERS]
    if unknown:
        print(f"unknown model(s): {unknown}; choose from {TRAINERS}")
        return 2
    for n in names:
        version, summary = _trainer(n)(approved)
        print(f"== {n} {version}\n{json.dumps(summary, indent=2, default=str)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

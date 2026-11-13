"""Train every Finora model, evaluate it honestly and save artefacts + metrics.

Usage:  python -m app.ml.train
Outputs: artifacts/*.joblib and artifacts/metrics.json
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import joblib

from ..config import ARTIFACTS_DIR
from ..database import SessionLocal
from . import anomaly, categoriser, credit_risk, forecast, peers, population

SEED = 7


def run(verbose: bool = True) -> dict:
    t0 = time.time()
    db = SessionLocal()
    try:
        pop = population.load(db)
    finally:
        db.close()
    metrics = {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seed": SEED,
               "population_users": int(len(pop["users"])), "population_transactions": int(len(pop["transactions"]))}
    steps = [("credit_risk", lambda: credit_risk.train(SEED)), ("categoriser", lambda: categoriser.train(SEED)),
             ("anomaly", lambda: anomaly.train(pop, SEED)), ("forecast", lambda: forecast.train(pop, SEED)),
             ("peers", lambda: peers.train(pop, SEED))]
    for name, fn in steps:
        t = time.time()
        art, m = fn()
        m["training_seconds"] = round(time.time() - t, 1)
        joblib.dump(art, ARTIFACTS_DIR / f"{name}.joblib")
        metrics[name] = m
        if verbose:
            print(f"  trained {name:<12} in {m['training_seconds']:>5}s")
    (ARTIFACTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    if verbose:
        print(f"All models trained in {time.time() - t0:.1f}s -> {ARTIFACTS_DIR}")
    return metrics


if __name__ == "__main__":
    run()

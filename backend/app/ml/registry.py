"""Loads trained model artefacts once and keeps them in memory."""
from __future__ import annotations

import json
from functools import lru_cache

import joblib

from ..config import ARTIFACTS_DIR

NAMES = ["credit_risk", "categoriser", "anomaly", "forecast", "peers"]


@lru_cache(maxsize=None)
def get(name: str):
    path = ARTIFACTS_DIR / f"{name}.joblib"
    if not path.exists():
        raise FileNotFoundError(f"Model '{name}' is not trained yet. Run: python -m app.ml.train")
    return joblib.load(path)


def metrics() -> dict:
    path = ARTIFACTS_DIR / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else {}


def status() -> dict:
    return {n: (ARTIFACTS_DIR / f"{n}.joblib").exists() for n in NAMES}


def reload():
    get.cache_clear()

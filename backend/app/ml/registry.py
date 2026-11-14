"""Loads the APPROVED real-data model of each kind, once, and keeps it in memory.

Only versions listed in artifacts/active.json are loaded, after checking the file's SHA-256 against its provenance record.
A model with no approved version raises ModelUnavailable ("awaiting real-data training"); the app shows that state and never
silently falls back to the legacy synthetic-trained artifacts.

Rollback for development only: MODEL_SET=legacy-synthetic loads artifacts/legacy-synthetic-2026-11-13/<name>.joblib and every
result is then labelled as synthetic-trained (see status()).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

import joblib

from ..config import ARTIFACTS_DIR
from . import provenance as PV

NAMES = ["credit_risk", "categoriser", "anomaly", "forecast", "peers"]
LEGACY_DIR = ARTIFACTS_DIR / "legacy-synthetic-2026-11-13"


class ModelUnavailable(FileNotFoundError):
    """No approved real-data version of this model yet."""


def model_set() -> str:
    return os.getenv("MODEL_SET", "real").strip().lower()


@lru_cache(maxsize=None)
def get(name: str):
    if model_set() == "legacy-synthetic":
        path = LEGACY_DIR / f"{name}.joblib"
        if not path.exists():
            raise ModelUnavailable(f"Legacy artifact for '{name}' not found.")
        return joblib.load(path)
    entry = PV.active().get(name)
    if not entry:
        raise ModelUnavailable(f"'{name}' has no approved (active) real-data version.")
    path = ARTIFACTS_DIR / entry["path"]
    if not path.exists() or PV.sha256(path) != entry["sha256"]:
        raise ModelUnavailable(f"'{name}' artifact is missing or does not match its recorded checksum.")
    return joblib.load(path)


def provenance(name: str) -> dict | None:
    entry = PV.active().get(name)
    if not entry:
        return None
    p = ARTIFACTS_DIR / entry["path"].rsplit("/", 1)[0] / "provenance.json"
    return json.loads(p.read_text()) if p.exists() else None


def metrics() -> dict:
    """Metrics of the ACTIVE real-data models, keyed by model (plus their provenance under '_provenance')."""
    out, prov = {}, {}
    for n in NAMES:
        entry = PV.active().get(n)
        if not entry:
            continue
        folder = ARTIFACTS_DIR / entry["path"].rsplit("/", 1)[0]
        if (folder / "metrics.json").exists():
            out[n] = json.loads((folder / "metrics.json").read_text())
        if (folder / "provenance.json").exists():
            prov[n] = json.loads((folder / "provenance.json").read_text())
    if out:
        out["_provenance"] = prov
    return out


def status() -> dict:
    """name -> True when an approved real-data model is available (legacy set: True with a synthetic label elsewhere)."""
    if model_set() == "legacy-synthetic":
        return {n: (LEGACY_DIR / f"{n}.joblib").exists() for n in NAMES}
    act = PV.active()
    return {n: n in act for n in NAMES}


def reload():
    get.cache_clear()


# ---------------------------------------------------------------- Model Lab
STATUS_TEXT = {
    "verified_real": "Available: real data, passed its acceptance criteria",
    "suggestion_only": "Available, suggestion only: passed its criteria; you confirm every category it suggests",
    "experimental": "Available, experimental: real data, did not meet its acceptance criteria (shown with the comparison)",
    "not_human_validated": "Available, experimental: real data, not human-validated yet",
    "trained_not_active": "Trained on real data, not switched on",
    "awaiting_training": "Not available: no real-data version trained yet",
    "benchmark": "Research benchmark only: not a Finora feature",
    "legacy_synthetic": "Legacy synthetic-trained artifact (development rollback only)",
}
LAB_ORDER = NAMES + ["anomaly_ulb_benchmark"]


def _versions(name: str) -> list[str]:
    d = PV.REAL_DIR / name
    return sorted(p.name for p in d.iterdir() if (p / "provenance.json").exists()) if d.exists() else []


def _read(folder, fname):
    p = folder / fname
    return json.loads(p.read_text()) if p.exists() else None


def _policy(name: str, active: bool) -> str | None:
    if name == "categoriser" and active:
        from . import categoriser
        if categoriser.SUGGESTION_ONLY:
            return ("Suggestion-only: every category it assigns is shown as a suggestion that you accept, reject or change. It passes "
                    "its criteria on US card data, but on Indian-format narrations its confident predictions agreed with the intended "
                    "category only about 44% of the time, so it is not presented as dependable.")
    entry = PV.active().get(name) or {}
    if entry.get("status") == "experimental":
        return entry.get("experimental_reason")
    return None


def lab() -> dict:
    """Everything Model Lab shows: one entry per model with its status, active/latest version, provenance and metrics."""
    from ..config import OLLAMA_MODEL
    from . import acceptance
    act, legacy = PV.active(), model_set() == "legacy-synthetic"
    models = []
    for n in LAB_ORDER:
        versions = _versions(n)
        entry = act.get(n)
        version = entry["version"] if entry else (versions[-1] if versions else None)
        folder = PV.REAL_DIR / n / version if version else None
        prov = _read(folder, "provenance.json") if folder else None
        met = PV.load_metrics(folder) if folder and (folder / "metrics.json").exists() else None
        passed, checks = acceptance.check(n, met) if met else (False, [])
        if legacy and n in NAMES:
            status = "legacy_synthetic"
        elif n == "anomaly_ulb_benchmark":
            status = "benchmark" if prov else "awaiting_training"
        elif entry and entry.get("status", "accepted") == "experimental":
            status = "not_human_validated" if n == "anomaly" else "experimental"
        elif entry:
            from . import categoriser
            status = "suggestion_only" if n == "categoriser" and categoriser.SUGGESTION_ONLY else "verified_real"
        elif not prov:
            status = "awaiting_training"
        else:
            status = "trained_not_active"
        models.append({"name": n, "status": status, "status_text": STATUS_TEXT[status], "active": bool(entry),
                       "activation_status": (entry or {}).get("status", "accepted") if entry else None,
                       "version": version, "all_versions": versions, "activated_at": (entry or {}).get("activated_at"),
                       "activation_reason": (entry or {}).get("reason"), "label": (prov or {}).get("deployment_label"),
                       "acceptance": {"passed": passed, "checks": checks} if met else None,
                       "deployment_policy": _policy(n, bool(entry)),
                       "provenance": prov, "metrics": met})
    return {
        "model_set": model_set(), "models": models,
        "rollback_history": act.get("_history", []),
        "ai_cfo": {"name": "AI CFO", "status": "pretrained", "trained_by_finora": False,
                   "family": "Qwen 2.5 (Alibaba Qwen team), served locally by Ollama",
                   "installed_tag": "qwen2.5:3b", "installed_digest": "357c53fb659c", "installed_size": "1.9 GB",
                   "configured_model": OLLAMA_MODEL,
                   "discrepancy": None if OLLAMA_MODEL == "qwen2.5:3b" else
                   f"The configuration selects '{OLLAMA_MODEL}', which is not the installed Qwen 2.5 model. "
                   "Left unchanged in Phase 6; resolved in Phase 7.",
                   "note": "Writes explanations only; every number comes from Finora's calculations."},
    }

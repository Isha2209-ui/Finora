"""Training provenance: the environment, datasets, artifact and metrics of every training run, written next to the model.

Layout:  artifacts/real/<model>/<version>/{model.joblib, metrics.json, provenance.json}
         artifacts/active.json  -> which version of each model the app loads (only real-data, evaluated, approved versions)
"""
from __future__ import annotations

import hashlib
import json
import platform
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import joblib

from ..config import ARTIFACTS_DIR, DATASETS_DIR

REAL_DIR = ARTIFACTS_DIR / "real"
ACTIVE = ARTIFACTS_DIR / "active.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def source_record(key: str) -> dict:
    p = DATASETS_DIR / "raw" / key / "SOURCE.json"
    return json.loads(p.read_text()) if p.exists() else {}


def environment() -> dict:
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, timeout=5).stdout.strip() or None
        except Exception:  # noqa: BLE001
            return None
    libs = {}
    for lib in ("scikit-learn", "xgboost", "pandas", "numpy", "shap", "scipy", "joblib"):
        try:
            libs[lib] = metadata.version(lib)
        except metadata.PackageNotFoundError:
            pass
    mem = sysctl("hw.memsize")
    return {"machine": sysctl("hw.model"), "chip": sysctl("machdep.cpu.brand_string"), "cpu_cores": sysctl("hw.ncpu"),
            "memory_gb": round(int(mem) / 2 ** 30, 1) if mem and mem.isdigit() else None,
            "os": f"{platform.system()} {platform.mac_ver()[0] or platform.release()}", "python": sys.version.split()[0],
            "libraries": libs, "accelerator": "CPU (XGBoost and scikit-learn do not use the Apple GPU/MPS here)",
            "trained_locally": True, "remote_services_used": False}


class Run:
    """Context for one training run: timing, peak memory, then save model + metrics + provenance."""

    def __init__(self, model: str, command: str):
        self.model, self.command = model, command
        self.version = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M%S")
        self.started = datetime.now(timezone.utc)
        self.t0 = time.time()

    def save(self, artifact: dict, metrics: dict, provenance: dict) -> Path:
        out = REAL_DIR / self.model / self.version
        out.mkdir(parents=True, exist_ok=True)
        path = out / "model.joblib"
        joblib.dump(artifact, path)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS
        rec = {"model": self.model, "version": self.version, "command": self.command,
               "training_started": self.started.isoformat(timespec="seconds"),
               "training_finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "training_seconds": round(time.time() - self.t0, 1), "peak_memory_mb": round(peak / 2 ** 20, 1),
               "environment": environment(), "artifact": {"path": str(path.relative_to(ARTIFACTS_DIR)), "sha256": sha256(path),
                                                           "bytes": path.stat().st_size},
               **provenance}
        (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
        (out / "provenance.json").write_text(json.dumps(rec, indent=2, default=str))
        return out


def load_metrics(folder: Path) -> dict:
    """metrics.json of a version, plus the blinded human-review result (review_result.json) when one has been computed.
    Training metrics are never rewritten after the run."""
    m = json.loads((folder / "metrics.json").read_text())
    rr = folder / "review_result.json"
    if rr.exists():
        m.setdefault("human_review", {})["result"] = json.loads(rr.read_text())
    return m


def active() -> dict:
    return json.loads(ACTIVE.read_text()) if ACTIVE.exists() else {}


def _write_active(cur: dict) -> None:
    tmp = ACTIVE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=2))
    tmp.replace(ACTIVE)                                     # atomic swap: the app never reads a half-written file


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


EXPERIMENTAL_REASONS = {
    "forecast": "Available as EXPERIMENTAL: on its chronological test it did not beat the 3-month moving average.",
    "anomaly": "Available as EXPERIMENTAL, NOT HUMAN-VALIDATED: the blinded human review of its flags is not complete.",
    "categoriser": "Available as SUGGESTION ONLY: not validated on Indian bank narrations.",
}


def activate(model: str, version: str, reason: str, experimental: bool = False) -> dict:
    """Point the app at a version.

    status "accepted"     - refused unless provenance says real data, evaluated and owner-approved, the artifact matches its
                            SHA-256, and the recorded metrics pass the model's PREDEFINED acceptance criteria.
    status "experimental" - (experimental=True) the same real-data / approval / checksum / not-a-benchmark checks, but the
                            acceptance criteria may be unmet. The unmet criteria are recorded in active.json and every output
                            of the model carries the experimental status, so it is never presented as validated.
    The replaced version is kept in _history for rollback."""
    from . import acceptance
    folder = REAL_DIR / model / version
    prov = json.loads((folder / "provenance.json").read_text())
    if prov.get("data_status") != "real" or not prov.get("approved_by_owner"):
        raise RuntimeError(f"{model} {version}: not activatable (data_status={prov.get('data_status')}, "
                           f"approved={prov.get('approved_by_owner')})")
    if prov.get("deployable") is False:
        raise RuntimeError(f"{model} {version}: not activatable (benchmark only, not deployable)")
    if sha256(ARTIFACTS_DIR / prov["artifact"]["path"]) != prov["artifact"]["sha256"]:
        raise RuntimeError(f"{model} {version}: artifact checksum does not match its provenance record")
    passed, checks = acceptance.check(model, load_metrics(folder))
    if not experimental and (not passed or not prov.get("evaluation_passed")):
        failed = "; ".join(f"{c['criterion']} ({c['value']})" for c in checks if not c["passed"]) or "evaluation_passed is false"
        raise RuntimeError(f"{model} {version}: not activatable, fails acceptance criteria: {failed}")
    status = "accepted" if (passed and prov.get("evaluation_passed")) else "experimental"
    cur = active()
    hist = cur.get("_history", [])
    hist.append({"model": model, "action": "activate", "status": status, "version": version, "previous": cur.get(model),
                 "at": _now(), "reason": reason})
    cur[model] = {"version": version, "path": prov["artifact"]["path"], "sha256": prov["artifact"]["sha256"],
                  "activated_at": _now(), "reason": reason, "label": prov.get("deployment_label"), "status": status,
                  "acceptance": checks, "unmet_criteria": [c["criterion"] for c in checks if not c["passed"]],
                  "experimental_reason": EXPERIMENTAL_REASONS.get(model) if status == "experimental" else None}
    cur["_history"] = hist
    _write_active(cur)
    return cur[model]


def status_of(model: str) -> str | None:
    """'accepted' | 'experimental' | None (not active)."""
    e = active().get(model)
    return None if not e else e.get("status", "accepted")


def deactivate(model: str, reason: str) -> dict | None:
    """Stop loading a model (the app then shows 'awaiting an approved model'). Files are kept; the entry goes to history."""
    cur = active()
    prev = cur.pop(model, None)
    if prev is None:
        return None
    cur.setdefault("_history", []).append({"model": model, "action": "deactivate", "previous": prev, "at": _now(), "reason": reason})
    _write_active(cur)
    return prev


def rollback(model: str, reason: str) -> dict | None:
    """Restore the entry that was active before the latest change to this model (re-verifying its checksum)."""
    cur = active()
    hist = cur.get("_history", [])
    last = next((h for h in reversed(hist) if h["model"] == model and h.get("action") != "rollback"), None)
    if last is None:
        raise RuntimeError(f"{model}: nothing to roll back to")
    prev = last.get("previous")
    if prev and sha256(ARTIFACTS_DIR / prev["path"]) != prev["sha256"]:
        raise RuntimeError(f"{model}: the previous artifact no longer matches its checksum")
    hist.append({"model": model, "action": "rollback", "previous": cur.get(model), "restored": prev, "at": _now(), "reason": reason})
    if prev:
        cur[model] = prev
    else:
        cur.pop(model, None)
    cur["_history"] = hist
    _write_active(cur)
    return prev

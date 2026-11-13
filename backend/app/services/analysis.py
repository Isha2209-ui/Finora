"""Runs the complete Finora analysis for one person and stores the results."""
from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import models as M
from ..ml import anomaly, credit_risk, forecast, peers, registry
from . import calculations as C
from . import recommendations as R
from .loader import load_identity
from .snapshot import build


def clean_json(o):
    """Make any result JSON-safe (NaN/inf -> None, numpy -> python)."""
    if isinstance(o, dict):
        return {str(k): clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except Exception:
            pass
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return o


def run(db: Session, uid: int, save: bool = True, fire_overrides: dict | None = None) -> dict:
    ident = load_identity(db, uid)
    snap = build(ident, fire_overrides)
    monthly, _, _ = C.monthly_frame(ident)
    ml, errors = {}, {}
    steps = {
        "credit_risk": lambda: credit_risk.analyse(registry.get("credit_risk"), ident),
        "anomaly": lambda: anomaly.analyse(registry.get("anomaly"), ident),
        "forecast": lambda: forecast.analyse(registry.get("forecast"), ident, monthly, snap),
        "peers": lambda: peers.analyse(registry.get("peers"), ident, monthly),
    }
    for name, fn in steps.items():
        try:
            ml[name] = fn()
        except FileNotFoundError as e:
            errors[name] = str(e)
        except Exception as e:  # one model failing must not take down the analysis
            errors[name] = f"{type(e).__name__}: {e}"
    recs = R.build(snap, ml)
    result = clean_json({**snap, "ml": ml, "ml_errors": errors, "recommendations": recs,
                         "alerts": R.alerts(snap, ml, recs), "generated_at": datetime.utcnow().isoformat(timespec="seconds")})
    if save:
        db.execute(delete(M.AnalysisResult).where(M.AnalysisResult.user_id == uid))
        db.execute(delete(M.Recommendation).where(M.Recommendation.user_id == uid, M.Recommendation.status == "open"))
        for comp in ["cash_flow", "net_worth", "credit", "debt", "fire", "health_score"]:
            db.add(M.AnalysisResult(user_id=uid, component=comp, result=result[comp]))
        for name, res in result["ml"].items():
            slim = {k: v for k, v in res.items() if k != "scores"}
            db.add(M.AnalysisResult(user_id=uid, component=f"ml:{name}", result=slim))
        kept = {r.code for r in db.query(M.Recommendation).filter(M.Recommendation.user_id == uid).all()}
        for r in result["recommendations"]:
            if r["code"] not in kept:
                db.add(M.Recommendation(user_id=uid, **r))
        db.commit()
    return result

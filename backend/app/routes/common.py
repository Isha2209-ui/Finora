"""Shared helpers for API routes: the per-profile analysis cache and public profile view. Access checks live in app/auth.py."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as M
from ..services import analysis
from ..services.loader import load_identity

_cache: dict[int, dict] = {}


def get_analysis(db: Session, user: M.User, refresh: bool = False) -> dict:
    if refresh or user.id not in _cache:
        _cache[user.id] = analysis.run(db, user.id, save=True)
    return _cache[user.id]


def invalidate(uid: int | None = None):
    if uid is None:
        _cache.clear()
    else:
        _cache.pop(uid, None)


def cfo_context(db: Session, user: M.User) -> dict:
    """Everything the AI CFO's tools may read, built FRESH for each message from the signed-in account's selected profile
    (the route has already checked access). Tools only ever see this dict, never the database."""
    from .plan import _accepted, _goals
    acc, dismissed = _accepted(db, user.id)
    return {"analysis": get_analysis(db, user), "identity": load_identity(db, user.id), "goals": _goals(db, user.id),
            "accepted": acc, "dismissed": dismissed}


def public_profile(u: M.User) -> dict:
    return {"internal_id": u.internal_id, "pan_masked": u.pan_masked, "name": u.name, "age": u.age,
            "occupation": u.occupation, "employment_type": u.employment_type, "city": u.city,
            "retirement_age_target": u.retirement_age_target, "is_demo": u.is_demo, "kind": u.kind,
            "read_only": u.kind == "template", "expires_at": u.expires_at.isoformat() if u.expires_at else None}

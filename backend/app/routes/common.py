"""Shared helpers for API routes: user lookup and the per-user analysis cache."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..services import analysis
from ..services.loader import load_identity

_cache: dict[int, dict] = {}


def get_user(db: Session, internal_id: str) -> M.User:
    user = db.scalar(select(M.User).where(M.User.internal_id == internal_id))
    if user is None:
        raise HTTPException(404, f"Profile '{internal_id}' not found.")
    return user


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
    return {"analysis": get_analysis(db, user), "identity": load_identity(db, user.id)}


def public_profile(u: M.User) -> dict:
    return {"internal_id": u.internal_id, "pan_masked": u.pan_masked, "name": u.name, "age": u.age,
            "occupation": u.occupation, "employment_type": u.employment_type, "city": u.city,
            "retirement_age_target": u.retirement_age_target, "is_demo": u.is_demo}

"""Authentication, CSRF and ownership checks, as FastAPI dependencies.

Every profile route depends on `profile_reader` or `profile_writer`. They resolve the signed-in account from the
session cookie, check CSRF for state-changing requests, and then check that the account may use the profile:

  kind        read                          write
  template    any signed-in account         nobody (403) - templates are never changed through the API
  population  nobody (404)                  nobody (404)
  sandbox     its owner only (else 404)     its owner only
  private     its owner only (else 404)     its owner only

"Not yours" answers 404, not 403, so profile IDs cannot be probed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config as CFG
from . import models as M
from . import security as SEC
from .database import get_db

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def audit(db: Session, action: str, *, request: Request | None = None, app_user_id: int | None = None,
          profile_id: int | None = None, outcome: str = "ok", detail: dict | None = None, commit: bool = True):
    """Write one audit row. `detail` must contain IDs/counts only (no PAN, password, token, amount or narration)."""
    db.add(M.AuditEvent(app_user_id=app_user_id, profile_id=profile_id, action=action, outcome=outcome, detail=detail,
                        ip_hash=SEC.ip_hash(client_ip(request), CFG.AUDIT_IP_SALT) if request else None))
    if commit:
        db.commit()


# ---------------------------------------------------------------- sessions
def start_session(db: Session, response: Response, user: M.AppUser, request: Request) -> M.AuthSession:
    token, csrf = SEC.new_token(), SEC.new_token()
    now = datetime.utcnow()
    s = M.AuthSession(app_user_id=user.id, token_hash=SEC.token_hash(token), csrf_token=csrf, created_at=now, last_seen_at=now,
                      expires_at=now + timedelta(hours=CFG.SESSION_TTL_HOURS),
                      user_agent=(request.headers.get("user-agent") or "")[:160])
    db.add(s)
    user.last_login_at = now
    db.commit()
    set_cookies(response, token, csrf)
    return s


def set_cookies(response: Response, token: str, csrf: str):
    age = CFG.SESSION_TTL_HOURS * 3600
    response.set_cookie(CFG.SESSION_COOKIE, token, max_age=age, httponly=True, secure=CFG.COOKIE_SECURE, samesite="lax", path="/")
    # Readable by the page so it can echo it in the X-CSRF-Token header (double-submit, bound to the session row).
    response.set_cookie(CFG.CSRF_COOKIE, csrf, max_age=age, httponly=False, secure=CFG.COOKIE_SECURE, samesite="lax", path="/")


def clear_cookies(response: Response):
    for name in (CFG.SESSION_COOKIE, CFG.CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=CFG.COOKIE_SECURE, samesite="lax")


def _load_session(db: Session, request: Request) -> M.AuthSession | None:
    token = request.cookies.get(CFG.SESSION_COOKIE)
    if not token or len(token) > 200:
        return None
    s = db.scalar(select(M.AuthSession).where(M.AuthSession.token_hash == SEC.token_hash(token)))
    if s is None or s.revoked or s.expires_at <= datetime.utcnow():
        return None
    return s


@dataclass
class Current:
    user: M.AppUser
    session: M.AuthSession


def current_account(request: Request, db: Session = Depends(get_db)) -> Current:
    """The signed-in account. 401 if there is no valid session; 403 if a state-changing request lacks the CSRF token."""
    s = _load_session(db, request)
    if s is None:
        raise HTTPException(401, "Please sign in.")
    if request.method in UNSAFE and not SEC.same(request.headers.get(CFG.CSRF_HEADER), s.csrf_token):
        raise HTTPException(403, "Missing or invalid CSRF token. Reload the page and try again.")
    user = db.get(M.AppUser, s.app_user_id)
    if user is None:
        raise HTTPException(401, "Please sign in.")
    now = datetime.utcnow()
    if (now - s.last_seen_at).total_seconds() > 300:  # avoid a write on every request
        s.last_seen_at = now
        db.commit()
    return Current(user, s)


def optional_account(request: Request, db: Session = Depends(get_db)) -> Current | None:
    try:
        return current_account(request, db)
    except HTTPException:
        return None


# ---------------------------------------------------------------- ownership
TEMPLATE_READ_ONLY = ("Demo identities are read-only templates. Open the demo with 'Explore demo identity' to get "
                      "your own editable copy, or build your own profile.")


def can_read(profile: M.User, account: M.AppUser) -> bool:
    if profile.kind == "template":
        return True
    if profile.kind in ("sandbox", "private"):
        if profile.owner_id is None or profile.owner_id != account.id:
            return False
        return not (profile.kind == "sandbox" and profile.expires_at and profile.expires_at <= datetime.utcnow())
    return False  # population and anything unknown


def can_write(profile: M.User, account: M.AppUser) -> bool:
    return profile.kind in ("sandbox", "private") and can_read(profile, account)


def load_profile(db: Session, internal_id: str, account: M.AppUser, write: bool = False) -> M.User:
    profile = db.scalar(select(M.User).where(M.User.internal_id == internal_id))
    if profile is None or not can_read(profile, account):
        raise HTTPException(404, f"Profile '{internal_id}' not found.")
    if write and not can_write(profile, account):
        raise HTTPException(403, TEMPLATE_READ_ONLY)
    return profile


@dataclass
class ProfileCtx:
    profile: M.User
    account: M.AppUser


def profile_reader(internal_id: str, cur: Current = Depends(current_account), db: Session = Depends(get_db)) -> ProfileCtx:
    return ProfileCtx(load_profile(db, internal_id, cur.user), cur.user)


def profile_writer(internal_id: str, cur: Current = Depends(current_account), db: Session = Depends(get_db)) -> ProfileCtx:
    return ProfileCtx(load_profile(db, internal_id, cur.user, write=True), cur.user)


# ---------------------------------------------------------------- rate limits
def rate_limit(key: str, limit: int, window: int, message: str = "Too many requests. Please wait and try again."):
    ok, retry = SEC.limiter.hit(key, limit, window)
    if not ok:
        raise HTTPException(429, f"{message} (retry in {retry}s)", headers={"Retry-After": str(retry)})

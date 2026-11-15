"""Accounts: register, sign in, sign out, current account, own activity log."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config as CFG
from .. import models as M
from .. import security as SEC
from ..auth import Current, audit, clear_cookies, client_ip, current_account, rate_limit, start_session
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["Accounts"])

BAD_LOGIN = "E-mail or password is incorrect."


class RegisterIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=SEC.PASSWORD_MAX)
    display_name: str = Field("", max_length=80)


class LoginIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=SEC.PASSWORD_MAX)


def account_out(u: M.AppUser, s: M.AuthSession) -> dict:
    return {"account": {"id": u.id, "email": u.email, "display_name": u.display_name, "is_guest": u.is_guest,
                        "created_at": u.created_at.isoformat()},
            "csrf_token": s.csrf_token, "session_expires_at": s.expires_at.isoformat(), "password_scheme": SEC.PASSWORD_SCHEME}


@router.post("/register", summary="Create an account (e-mail + password) and sign in")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if CFG.REGISTER_IP_MAX > 0:                      # off by default; opt-in for a public deployment (see config.py)
        rate_limit(f"register:{client_ip(request)}", CFG.REGISTER_IP_MAX, 3600, "Too many sign-ups from this address.")
    email = SEC.normalise_email(body.email)
    if not SEC.EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid e-mail address.")
    problem = SEC.password_problem(body.password, email)
    if problem:
        raise HTTPException(422, problem)
    if db.scalar(select(M.AppUser.id).where(M.AppUser.email == email)):
        raise HTTPException(409, "An account with this e-mail already exists. Sign in instead.")
    u = M.AppUser(email=email, password_hash=SEC.hash_password(body.password), display_name=body.display_name.strip())
    db.add(u)
    db.flush()
    audit(db, "account.register", request=request, app_user_id=u.id, commit=False)
    s = start_session(db, response, u, request)
    return account_out(u, s)


@router.post("/login", summary="Sign in")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    email = SEC.normalise_email(body.email)
    ip_key = f"login-ip-fail:{ip}"             # only FAILED attempts count against an IP: stops password spraying, never blocks real sign-ins
    ip_blocked, ip_retry = SEC.limiter.blocked(ip_key, CFG.LOGIN_IP_MAX_ATTEMPTS, CFG.LOGIN_WINDOW_SECONDS)
    if ip_blocked:
        raise HTTPException(429, f"Too many sign-in attempts. (retry in {ip_retry}s)", headers={"Retry-After": str(ip_retry)})
    fail_key = f"login-fail:{SEC.token_hash(email)}"
    blocked, retry = SEC.limiter.blocked(fail_key, CFG.LOGIN_MAX_FAILURES, CFG.LOGIN_WINDOW_SECONDS)
    if blocked:
        audit(db, "account.login", request=request, outcome="denied", detail={"reason": "locked"})
        raise HTTPException(429, f"Too many failed attempts for this account. Try again in {retry}s.",
                            headers={"Retry-After": str(retry)})
    u = db.scalar(select(M.AppUser).where(M.AppUser.email == email, M.AppUser.is_guest.is_(False)))
    ok = SEC.verify_password(u.password_hash if u else SEC.DUMMY_HASH, body.password)
    if not (u and ok):
        SEC.limiter.add(fail_key)
        SEC.limiter.add(ip_key)
        audit(db, "account.login", request=request, app_user_id=u.id if u else None, outcome="failed")
        raise HTTPException(401, BAD_LOGIN)
    SEC.limiter.clear(fail_key)
    if SEC.needs_rehash(u.password_hash):
        u.password_hash = SEC.hash_password(body.password)
    audit(db, "account.login", request=request, app_user_id=u.id, commit=False)
    s = start_session(db, response, u, request)
    return account_out(u, s)


@router.post("/logout", summary="Sign out (revokes this session)")
def logout(request: Request, response: Response, cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    cur.session.revoked = True
    audit(db, "account.logout", request=request, app_user_id=cur.user.id)
    clear_cookies(response)
    return {"signed_out": True}


@router.get("/me", summary="The signed-in account (401 if not signed in)")
def me(cur: Current = Depends(current_account)):
    return account_out(cur.user, cur.session)


@router.get("/activity", summary="Your own recent security and data events (audit log)")
def activity(cur: Current = Depends(current_account), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.AuditEvent).where(M.AuditEvent.app_user_id == cur.user.id)
                      .order_by(M.AuditEvent.id.desc()).limit(50)).all()
    return [{"action": r.action, "outcome": r.outcome, "profile_id": r.profile_id, "detail": r.detail,
             "at": r.created_at.isoformat()} for r in rows]

"""Finora API - AI-powered personal financial intelligence.

Run:   uvicorn app.main:app --reload --port 8001
Docs:  http://127.0.0.1:8001/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select

from . import migrate, process_lock
from . import models as M
from .cfo import llm
from .config import CORS_ORIGINS, CSRF_HEADER, DATABASE_URL, IS_PRODUCTION, SESSION_COOKIE
from .database import Base, SessionLocal, engine
from .ml import registry
from .routes import auth as auth_routes
from .routes import data, plan, planning, profiles, records, review, statements
from .security import install_log_scrubbing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """First run: create tables, load the demo data and train the models automatically."""
    install_log_scrubbing()
    process_lock.acquire(DATABASE_URL)          # exactly one server process per database (see app/process_lock.py)
    if not inspect(engine).has_table("users"):
        Base.metadata.create_all(engine)
    changes = migrate.run(engine)
    if changes:
        print(f"[finora] Database upgraded: {', '.join(changes)}")
    with SessionLocal() as db:
        empty = (db.scalar(select(func.count()).select_from(M.User)) or 0) == 0
    if empty:
        print("[finora] Empty database - seeding demo data (about 20 seconds)...")
        from .data import seed
        seed.run()
    with SessionLocal() as db:
        from .services import sandbox
        purged = sandbox.purge_expired(db)
    if purged:
        print(f"[finora] Removed {purged} expired demo sandbox(es).")
    with SessionLocal() as db:
        from .services import statement_import
        rolled = statement_import.recover_interrupted(db)
    if rolled:
        print(f"[finora] Rolled back {rolled} statement import(s) interrupted by a restart.")
    waiting = [n for n, ok in registry.status().items() if not ok]
    if waiting:   # never auto-train: real-data training needs approved datasets (python -m app.ml.train)
        print(f"[finora] No approved (active) real-data model: {', '.join(waiting)}. These features show as unavailable.")
    yield


app = FastAPI(title="Finora API", version="1.0.0", lifespan=lifespan,
              description="Financial identity, ML analysis, FIRE planning, decision simulation and an AI CFO. "
                          "All demo data is synthetic.")
# Credentialed CORS: only explicit origins (never "*"). In development the Vite proxy makes requests same-origin anyway.
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_origin_regex=None if IS_PRODUCTION else r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", CSRF_HEADER], expose_headers=["Content-Disposition"])


MULTIPART_OVERHEAD = 1_000_000


class UploadGuard:
    """Outermost guard for statement uploads, applied BEFORE any byte of the body is read or spooled to disk:
      * no session cookie            -> 401 (anonymous uploads never reach the form parser)
      * no Content-Length (chunked)  -> 411 (a declared size is required; the server rejects bodies longer than declared)
      * Content-Length over the limit -> 413
    Session validity, CSRF, ownership and the rate limit are still checked by the endpoint itself."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST" and (scope["path"].endswith("/imports") or scope["path"].endswith("/upload")):
            headers = {k.lower(): v for k, v in scope["headers"]}
            limit = (statements.UPLOAD_MAX_BYTES if scope["path"].endswith("/imports") else data.UPLOAD_MAX_BYTES) + MULTIPART_OVERHEAD
            cookie = headers.get(b"cookie", b"").decode("latin-1")
            raw_len = headers.get(b"content-length")
            if f"{SESSION_COOKIE}=" not in cookie:
                return await _reply(send, 401, "Please sign in.")
            if raw_len is None:
                return await _reply(send, 411, "Upload size must be declared (Content-Length).")
            try:
                size = int(raw_len)
            except ValueError:
                return await _reply(send, 400, "Invalid Content-Length.")
            if size > limit:
                return await _reply(send, 413, f"File too large (limit {(limit - MULTIPART_OVERHEAD) // 1_000_000} MB). "
                                               "Split the statement into smaller files.")
        return await self.app(scope, receive, send)


async def _reply(send, status: int, detail: str):
    import json
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/") and request.url.path not in ("/api/health",):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(auth_routes.router)
app.include_router(profiles.router)
app.include_router(planning.router)
app.include_router(data.router)
app.include_router(records.router)
app.include_router(statements.router)
app.include_router(plan.router)
app.include_router(review.router)
app.add_middleware(UploadGuard)      # outermost: runs before the body is read


@app.get("/api/health", tags=["System"], summary="Service status")
def health():
    with SessionLocal() as db:
        users = db.scalar(select(func.count()).select_from(M.User))
        tx = db.scalar(select(func.count()).select_from(M.Transaction))
    return {"status": "ok", "database": "postgresql" if DATABASE_URL.startswith("postgres") else "sqlite",
            "users": users, "transactions": tx, "models": registry.status(), "ai_cfo": llm.status()}

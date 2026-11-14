"""Finora API - AI-powered personal financial intelligence.

Run:   uvicorn app.main:app --reload --port 8001
Docs:  http://127.0.0.1:8001/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select

from . import migrate
from . import models as M
from .cfo import llm
from .config import CORS_ORIGINS, CSRF_HEADER, DATABASE_URL, IS_PRODUCTION
from .database import Base, SessionLocal, engine
from .ml import registry
from .routes import auth as auth_routes
from .routes import data, planning, profiles, records, statements
from .security import install_log_scrubbing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """First run: create tables, load the demo data and train the models automatically."""
    install_log_scrubbing()
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
    if not all(registry.status().values()):
        print("[finora] Models not found - training (about 40 seconds)...")
        from .ml import train
        train.run()
    yield


app = FastAPI(title="Finora API", version="1.0.0", lifespan=lifespan,
              description="Financial identity, ML analysis, FIRE planning, decision simulation and an AI CFO. "
                          "All demo data is synthetic. Educational guidance, not licensed financial advice.")
# Credentialed CORS: only explicit origins (never "*"). In development the Vite proxy makes requests same-origin anyway.
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_origin_regex=None if IS_PRODUCTION else r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", CSRF_HEADER], expose_headers=["Content-Disposition"])


MULTIPART_OVERHEAD = 1_000_000


@app.middleware("http")
async def upload_size_guard(request: Request, call_next):
    """Refuse an oversized statement upload from its Content-Length header, before the body is read or spooled to disk.
    (A chunked upload without Content-Length is still capped by the endpoint while it reads the file.)"""
    path = request.url.path
    if request.method == "POST" and (path.endswith("/imports") or path.endswith("/upload")):
        limit = (statements.UPLOAD_MAX_BYTES if path.endswith("/imports") else data.UPLOAD_MAX_BYTES) + MULTIPART_OVERHEAD
        try:
            size = int(request.headers.get("content-length") or 0)
        except ValueError:
            size = 0
        if size > limit:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": f"File too large (limit {(limit - MULTIPART_OVERHEAD) // 1_000_000} MB). "
                                           "Split the statement into smaller files."}, status_code=413)
    return await call_next(request)


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


@app.get("/api/health", tags=["System"], summary="Service status")
def health():
    with SessionLocal() as db:
        users = db.scalar(select(func.count()).select_from(M.User))
        tx = db.scalar(select(func.count()).select_from(M.Transaction))
    return {"status": "ok", "database": "postgresql" if DATABASE_URL.startswith("postgres") else "sqlite",
            "users": users, "transactions": tx, "models": registry.status(), "ai_cfo": llm.status()}

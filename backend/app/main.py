"""Finora API - AI-powered personal financial intelligence.

Run:   uvicorn app.main:app --reload --port 8001
Docs:  http://127.0.0.1:8001/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select

from . import models as M
from .cfo import llm
from .config import CORS_ORIGINS, DATABASE_URL
from .database import Base, SessionLocal, engine
from .ml import registry
from .routes import data, planning, profiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    """First run: create tables, load the demo data and train the models automatically."""
    if not inspect(engine).has_table("users"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        empty = (db.scalar(select(func.count()).select_from(M.User)) or 0) == 0
    if empty:
        print("[finora] Empty database - seeding demo data (about 20 seconds)...")
        from .data import seed
        seed.run()
    if not all(registry.status().values()):
        print("[finora] Models not found - training (about 40 seconds)...")
        from .ml import train
        train.run()
    yield


app = FastAPI(title="Finora API", version="1.0.0", lifespan=lifespan,
              description="Financial identity, ML analysis, FIRE planning, decision simulation and an AI CFO. "
                          "All demo data is synthetic. Educational guidance, not licensed financial advice.")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
app.include_router(profiles.router)
app.include_router(planning.router)
app.include_router(data.router)


@app.get("/api/health", tags=["System"], summary="Service status")
def health():
    with SessionLocal() as db:
        users = db.scalar(select(func.count()).select_from(M.User))
        tx = db.scalar(select(func.count()).select_from(M.Transaction))
    return {"status": "ok", "database": "postgresql" if DATABASE_URL.startswith("postgres") else "sqlite",
            "users": users, "transactions": tx, "models": registry.status(), "ai_cfo": llm.status()}

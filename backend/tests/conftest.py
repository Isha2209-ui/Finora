import os
import secrets

# Generous limits for the suite itself; the rate-limit tests lower them explicitly.
os.environ.setdefault("REGISTER_IP_MAX", "10000")
os.environ.setdefault("LOGIN_IP_MAX_ATTEMPTS", "10000")
os.environ.setdefault("CHAT_MAX_PER_MINUTE", "10000")
os.environ.setdefault("UPLOAD_MAX_PER_HOUR", "10000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app import models as M  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services.profile_ops import delete_profile_data  # noqa: E402

DEMO = {"ABCDE1234F": "FINORA_USER_001", "PQRST5678K": "FINORA_USER_002", "LMNOP2345D": "FINORA_USER_003", "XYZAB9876C": "FINORA_USER_004"}
TEST_DOMAIN = "tests.finora.invalid"   # every account the suite creates uses this domain and is removed afterwards
PASSWORD = "correct horse battery staple"


def new_email(tag: str = "user") -> str:
    return f"{tag}-{secrets.token_hex(4)}@{TEST_DOMAIN}"


def signed_in_client(tag: str = "user") -> TestClient:
    """A fresh browser: its own cookie jar, registered and signed in, CSRF header set."""
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": new_email(tag), "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


def _cleanup_test_accounts():
    with SessionLocal() as db:
        ids = [i for (i,) in db.execute(select(M.AppUser.id).where(M.AppUser.email.like(f"%@{TEST_DOMAIN}")))]
        if not ids:
            return
        for p in db.scalars(select(M.User).where(M.User.owner_id.in_(ids))).all():
            delete_profile_data(db, p)
        for model in (M.ChatMessage, M.Report):
            db.execute(delete(model).where(model.app_user_id.in_(ids)))
        db.execute(delete(M.AuditEvent).where(M.AuditEvent.app_user_id.in_(ids)))
        db.execute(delete(M.AuthSession).where(M.AuthSession.app_user_id.in_(ids)))
        db.execute(delete(M.AppUser).where(M.AppUser.id.in_(ids)))
        db.commit()


@pytest.fixture(scope="session", autouse=True)
def client():
    with TestClient(app) as c:     # runs startup (migration, seeding/training if needed)
        r = c.post("/api/auth/register", json={"email": new_email("suite"), "password": PASSWORD})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        yield c
    _cleanup_test_accounts()


@pytest.fixture(scope="session")
def analyses(client):
    return {uid: client.get(f"/api/profiles/{uid}/analysis").json() for uid in DEMO.values()}

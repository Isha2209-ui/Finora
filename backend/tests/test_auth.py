"""Accounts, sessions, CSRF, ownership isolation, rate limits, audit and log hygiene."""
import io
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config as CFG
from app import models as M
from app import security as SEC
from app.database import SessionLocal, engine
from app.main import app

from .conftest import PASSWORD, new_email, signed_in_client

PROFILE_ROUTES = [("get", "/api/profiles/{id}"), ("get", "/api/profiles/{id}/analysis"), ("post", "/api/profiles/{id}/analyze"),
                  ("get", "/api/profiles/{id}/accounts"), ("get", "/api/profiles/{id}/transactions"),
                  ("get", "/api/profiles/{id}/recommendations"), ("post", "/api/profiles/{id}/fire"),
                  ("post", "/api/profiles/{id}/payoff"), ("get", "/api/profiles/{id}/chat"), ("get", "/api/profiles/{id}/briefing"),
                  ("get", "/api/profiles/{id}/report.pdf"), ("get", "/api/profiles/{id}/export.zip"),
                  ("get", "/api/profiles/{id}/transactions.csv"), ("get", "/api/profiles/{id}/reports"),
                  ("get", "/api/profiles/{id}/data-summary"), ("patch", "/api/profiles/{id}"), ("delete", "/api/profiles/{id}")]


def _call(c, method, path, **kw):
    body = {"json": {}} if method in ("post", "patch") else {}
    return getattr(c, method)(path, **{**body, **kw})


@pytest.fixture(scope="module")
def alice():
    c = signed_in_client("alice")
    r = c.post("/api/profiles", json={"name": "Alice Private", "age": 31, "monthly_income": 120000, "bank_balance": 200000})
    assert r.status_code == 200, r.text
    c.profile_id = r.json()["profile"]["internal_id"]
    return c


@pytest.fixture(scope="module")
def bob():
    return signed_in_client("bob")


# ---------------------------------------------------------------- sign-in required
@pytest.mark.parametrize("method,path", PROFILE_ROUTES)
def test_profile_routes_need_sign_in(method, path):
    anon = TestClient(app)
    assert _call(anon, method, path.format(id="FINORA_USER_001")).status_code == 401


def test_lookup_and_list_need_sign_in():
    anon = TestClient(app)
    assert anon.post("/api/lookup", json={"pan": "ABCDE1234F"}).status_code == 401
    assert anon.get("/api/profiles").status_code == 401
    assert anon.post("/api/profiles", json={"name": "X Y", "age": 30, "monthly_income": 1}).status_code == 401
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get("/api/health").status_code == 200               # public, no personal data
    assert anon.get("/api/models/metrics").status_code == 200


# ---------------------------------------------------------------- registration & login
def test_register_validation():
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": "not-an-email", "password": PASSWORD}).status_code == 422
    assert c.post("/api/auth/register", json={"email": new_email(), "password": "short"}).status_code == 422
    assert c.post("/api/auth/register", json={"email": new_email(), "password": "password123"}).status_code == 422
    assert c.post("/api/auth/register", json={"email": new_email(), "password": "aaaaaaaaaaaa"}).status_code == 422
    e = new_email()
    r = c.post("/api/auth/register", json={"email": e.upper(), "password": PASSWORD})
    assert r.status_code == 200 and r.json()["account"]["email"] == e          # stored lower-cased
    assert PASSWORD not in r.text
    assert TestClient(app).post("/api/auth/register", json={"email": e, "password": PASSWORD}).status_code == 409


def test_password_is_stored_as_argon2id_hash():
    e = new_email("hash")
    TestClient(app).post("/api/auth/register", json={"email": e, "password": PASSWORD})
    with SessionLocal() as db:
        h = db.scalar(select(M.AppUser.password_hash).where(M.AppUser.email == e))
    assert h.startswith("$argon2id$") and PASSWORD not in h
    assert SEC.verify_password(h, PASSWORD) and not SEC.verify_password(h, PASSWORD + "x")


def test_login_logout_and_generic_errors():
    e = new_email("login")
    TestClient(app).post("/api/auth/register", json={"email": e, "password": PASSWORD})
    c = TestClient(app)
    wrong = c.post("/api/auth/login", json={"email": e, "password": "wrong password here"})
    unknown = c.post("/api/auth/login", json={"email": new_email("nobody"), "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]                  # does not reveal whether the account exists
    r = c.post("/api/auth/login", json={"email": e, "password": PASSWORD})
    assert r.status_code == 200
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    assert c.get("/api/auth/me").json()["account"]["email"] == e
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_logged_out_token_cannot_be_replayed():
    c = signed_in_client("replay")
    token = c.cookies.get(CFG.SESSION_COOKIE)
    c.post("/api/auth/logout")
    thief = TestClient(app, cookies={CFG.SESSION_COOKIE: token})
    assert thief.get("/api/auth/me").status_code == 401


def test_session_cookie_flags_and_hashed_storage():
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": new_email("cookie"), "password": PASSWORD})
    cookies = r.headers.get_list("set-cookie")
    sess = next(x for x in cookies if x.startswith(CFG.SESSION_COOKIE + "="))
    csrf = next(x for x in cookies if x.startswith(CFG.CSRF_COOKIE + "="))
    assert "HttpOnly" in sess and "samesite=lax" in sess.lower() and "Path=/" in sess
    assert "HttpOnly" not in csrf                                                # the page must read it to send the header
    token = c.cookies.get(CFG.SESSION_COOKIE)
    with SessionLocal() as db:
        assert db.scalar(select(M.AuthSession.id).where(M.AuthSession.token_hash == token)) is None
        assert db.scalar(select(M.AuthSession.id).where(M.AuthSession.token_hash == SEC.token_hash(token))) is not None


def test_expired_session_is_rejected():
    c = signed_in_client("expiry")
    token = c.cookies.get(CFG.SESSION_COOKIE)
    with SessionLocal() as db:
        s = db.scalar(select(M.AuthSession).where(M.AuthSession.token_hash == SEC.token_hash(token)))
        s.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    assert c.get("/api/auth/me").status_code == 401


def test_login_lockout_after_repeated_failures(monkeypatch):
    monkeypatch.setattr(CFG, "LOGIN_MAX_FAILURES", 3)
    e = new_email("lock")
    TestClient(app).post("/api/auth/register", json={"email": e, "password": PASSWORD})
    c = TestClient(app)
    for _ in range(3):
        assert c.post("/api/auth/login", json={"email": e, "password": "bad password 123"}).status_code == 401
    r = c.post("/api/auth/login", json={"email": e, "password": PASSWORD})          # even the right password is refused now
    assert r.status_code == 429 and "Retry-After" in r.headers
    SEC.limiter.clear(f"login-fail:{SEC.token_hash(e)}")
    assert c.post("/api/auth/login", json={"email": e, "password": PASSWORD}).status_code == 200


def test_register_rate_limit(monkeypatch):
    monkeypatch.setattr(CFG, "REGISTER_IP_MAX", 2)
    SEC.limiter.clear("register:testclient")
    c = TestClient(app)
    codes = [c.post("/api/auth/register", json={"email": new_email("rl"), "password": PASSWORD}).status_code for _ in range(3)]
    SEC.limiter.clear("register:testclient")
    assert codes == [200, 200, 429]


# ---------------------------------------------------------------- CSRF
def test_state_changing_requests_need_csrf_header(alice):
    pid = alice.profile_id
    token = alice.headers.pop("X-CSRF-Token")
    try:
        assert alice.patch(f"/api/profiles/{pid}", json={"age": 40}).status_code == 403
        assert alice.post(f"/api/profiles/{pid}/fire", json={}).status_code == 403
        assert alice.patch(f"/api/profiles/{pid}", json={"age": 40}, headers={"X-CSRF-Token": "forged"}).status_code == 403
        assert alice.get(f"/api/profiles/{pid}").status_code == 200              # reads do not need it
    finally:
        alice.headers["X-CSRF-Token"] = token
    assert alice.patch(f"/api/profiles/{pid}", json={"age": 32}).json()["age"] == 32


def test_csrf_token_of_another_session_is_rejected(alice, bob):
    pid = alice.profile_id
    r = alice.patch(f"/api/profiles/{pid}", json={"age": 33}, headers={"X-CSRF-Token": bob.headers["X-CSRF-Token"]})
    assert r.status_code == 403


# ---------------------------------------------------------------- ownership isolation
@pytest.mark.parametrize("method,path", PROFILE_ROUTES + [("post", "/api/profiles/{id}/chat"), ("post", "/api/profiles/{id}/decision")])
def test_other_account_cannot_touch_private_profile(alice, bob, method, path):
    url = path.format(id=alice.profile_id)
    kw = {"json": {"message": "What is my net worth?", "use_llm": False}} if path.endswith("/chat") and method == "post" else {}
    kw = {"json": {"price": 100000}} if path.endswith("/decision") else kw
    r = _call(bob, method, url, **kw)
    assert r.status_code == 404, (method, url, r.status_code)                  # 404, not 403: existence is not revealed
    assert alice.get(f"/api/profiles/{alice.profile_id}").status_code == 200


def test_other_account_cannot_write_into_private_profile(alice, bob):
    pid = alice.profile_id
    csv = b"Date,Narration,Withdrawal,Deposit\n05/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,500,\n"
    assert bob.post(f"/api/profiles/{pid}/upload", files={"file": ("s.csv", io.BytesIO(csv), "text/csv")}).status_code == 404
    assert bob.post(f"/api/profiles/{pid}/transactions", json={"date": "2026-10-01", "amount": 5, "description": "hack"}).status_code == 404
    tx = alice.post(f"/api/profiles/{pid}/transactions", json={"date": "2026-10-02", "amount": 250, "description": "UPI/DR/9/ZOMATO/HDFC/zomato@ybl"}).json()
    assert bob.patch(f"/api/profiles/{pid}/transactions/{tx['id']}", json={"category": "Rent"}).status_code == 404
    assert bob.delete(f"/api/profiles/{pid}/transactions/{tx['id']}").status_code == 404
    # bob's own profile cannot reach alice's transaction ID either
    bp = bob.post("/api/profiles", json={"name": "Bob Own", "age": 40, "monthly_income": 50000}).json()["profile"]["internal_id"]
    assert bob.patch(f"/api/profiles/{bp}/transactions/{tx['id']}", json={"category": "Rent"}).status_code == 404
    assert bob.delete(f"/api/profiles/{bp}/transactions/{tx['id']}").status_code == 404
    assert alice.delete(f"/api/profiles/{pid}/transactions/{tx['id']}").status_code == 200


def test_profile_list_shows_only_templates_and_own(alice, bob):
    a_ids = {p["internal_id"] for p in alice.get("/api/profiles").json()}
    b_ids = {p["internal_id"] for p in bob.get("/api/profiles").json()}
    assert alice.profile_id in a_ids and alice.profile_id not in b_ids
    assert {"FINORA_USER_001", "FINORA_USER_004"} <= a_ids & b_ids
    with SessionLocal() as db:
        pop = set(db.scalars(select(M.User.internal_id).where(M.User.kind == "population")))
    assert not (a_ids | b_ids) & pop


def test_training_population_is_never_reachable(bob):
    with SessionLocal() as db:
        pop_ids = db.scalars(select(M.User.internal_id).where(M.User.kind == "population").limit(3)).all()
    assert pop_ids
    for pid in pop_ids:
        assert bob.get(f"/api/profiles/{pid}").status_code == 404
        assert bob.get(f"/api/profiles/{pid}/transactions").status_code == 404


def test_templates_are_read_only(bob):
    uid = "FINORA_USER_002"
    assert bob.get(f"/api/profiles/{uid}/analysis").status_code == 200
    tx = bob.get(f"/api/profiles/{uid}/transactions", params={"limit": 1}).json()["items"][0]
    csv = b"Date,Narration,Withdrawal,Deposit\n05/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,500,\n"
    for r in [bob.patch(f"/api/profiles/{uid}", json={"age": 50}),
              bob.delete(f"/api/profiles/{uid}"),
              bob.patch(f"/api/profiles/{uid}/transactions/{tx['id']}", json={"category": "Rent"}),
              bob.delete(f"/api/profiles/{uid}/transactions/{tx['id']}"),
              bob.post(f"/api/profiles/{uid}/transactions", json={"date": "2026-10-01", "amount": 5, "description": "x y"}),
              bob.post(f"/api/profiles/{uid}/upload", files={"file": ("s.csv", io.BytesIO(csv), "text/csv")})]:
        assert r.status_code == 403
    after = bob.get(f"/api/profiles/{uid}/transactions", params={"limit": 1}).json()["items"][0]
    assert after["category"] == tx["category"]


def test_lookup_only_resolves_demo_identifiers_to_an_own_sandbox(alice):
    r = alice.post("/api/lookup", json={"pan": "ABCDE1234F"})
    assert r.status_code == 200 and r.json()["profile"]["kind"] == "sandbox" and not r.json()["profile"]["read_only"]
    assert alice.post("/api/lookup", json={"pan": "TESTP1234Q"}).status_code == 404


def test_chat_history_and_reports_are_per_account_even_on_templates(alice, bob):
    uid = "FINORA_USER_003"
    alice.delete(f"/api/profiles/{uid}/chat")
    bob.delete(f"/api/profiles/{uid}/chat")
    alice.post(f"/api/profiles/{uid}/chat", json={"message": "What is my net worth?", "use_llm": False})
    assert len(alice.get(f"/api/profiles/{uid}/chat").json()) == 2
    assert bob.get(f"/api/profiles/{uid}/chat").json() == []
    bob.delete(f"/api/profiles/{uid}/chat")                                      # bob clearing does not clear alice's
    assert len(alice.get(f"/api/profiles/{uid}/chat").json()) == 2
    assert alice.get(f"/api/profiles/{uid}/report.pdf").status_code == 200
    assert len(alice.get(f"/api/profiles/{uid}/reports").json()) >= 1
    assert bob.get(f"/api/profiles/{uid}/reports").json() == []


def test_account_can_delete_own_profile_and_everything_goes(bob):
    pid = bob.post("/api/profiles", json={"name": "Temp Bob", "age": 30, "monthly_income": 40000}).json()["profile"]["internal_id"]
    bob.post(f"/api/profiles/{pid}/transactions", json={"date": "2026-10-03", "amount": 99, "description": "UPI/DR/1/UBER/AXIS/uber@okaxis"})
    with SessionLocal() as db:
        db_id = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
    r = bob.delete(f"/api/profiles/{pid}")
    assert r.status_code == 200 and r.json()["rows_deleted"] >= 3
    with SessionLocal() as db:
        assert db.get(M.User, db_id) is None
        for model in (M.Transaction, M.IncomeRecord, M.BankAccount):
            assert db.scalar(select(model.id).where(model.user_id == db_id)) is None
    assert bob.get(f"/api/profiles/{pid}").status_code == 404


# ---------------------------------------------------------------- upload limits
def test_upload_size_limit(alice, monkeypatch):
    import app.routes.data as D
    monkeypatch.setattr(D, "UPLOAD_MAX_BYTES", 1000)
    big = b"Date,Narration,Withdrawal,Deposit\n" + b"05/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,500,\n" * 50
    r = alice.post(f"/api/profiles/{alice.profile_id}/upload", files={"file": ("big.csv", io.BytesIO(big), "text/csv")})
    assert r.status_code == 413


def test_upload_rate_limit(alice, monkeypatch):
    import app.routes.data as D
    monkeypatch.setattr(D, "UPLOAD_MAX_PER_HOUR", 2)
    key = f"upload:{alice.get('/api/auth/me').json()['account']['id']}"
    SEC.limiter.clear(key)
    bad = b"foo,bar\n1,2\n"
    codes = [alice.post(f"/api/profiles/{alice.profile_id}/upload", files={"file": ("x.csv", io.BytesIO(bad), "text/csv")}).status_code
             for _ in range(3)]
    SEC.limiter.clear(key)
    assert codes == [422, 422, 429]


# ---------------------------------------------------------------- privacy of training data
def test_private_profiles_are_never_used_for_training(alice):
    from app.ml import population
    with SessionLocal() as db:
        pop = population.load(db)
        kinds = set(db.scalars(select(M.User.kind).where(M.User.id.in_(pop["users"]["id"].tolist()))))
        private_id = db.scalar(select(M.User.id).where(M.User.internal_id == alice.profile_id))
    assert kinds == {"population"} and private_id not in set(pop["users"]["id"])


# ---------------------------------------------------------------- audit & logs
def test_audit_trail_records_actions_without_secrets(alice):
    me = alice.get("/api/auth/me").json()["account"]["id"]
    alice.get(f"/api/profiles/{alice.profile_id}/export.zip")
    acts = alice.get("/api/auth/activity").json()
    names = {a["action"] for a in acts}
    assert {"account.register", "profile.create", "data.export"} <= names
    with SessionLocal() as db:
        rows = db.scalars(select(M.AuditEvent).where(M.AuditEvent.app_user_id == me)).all()
    blob = " ".join(f"{r.action} {r.detail} {r.ip_hash}" for r in rows)
    assert PASSWORD not in blob and "@" not in blob and "testclient" not in blob


def test_failed_logins_are_audited_without_email():
    e = new_email("auditfail")
    TestClient(app).post("/api/auth/login", json={"email": e, "password": "nope nope nope"})
    with SessionLocal() as db:
        last = db.scalars(select(M.AuditEvent).where(M.AuditEvent.action == "account.login").order_by(M.AuditEvent.id.desc())).first()
    assert last.outcome == "failed" and e not in str(last.detail)


def test_log_scrubbing_redacts_sensitive_values(caplog):
    line = ("lookup ABCDE1234F card 4521 1234 5678 9012 acct 123456789012 user a.b@example.com "
            "cookie finora_session=abcDEF123_- password=hunter22 on 2026-10")
    clean = SEC.scrub(line)
    for secret in ["ABCDE1234F", "4521 1234 5678 9012", "123456789012", "a.b@example.com", "abcDEF123_-", "hunter22"]:
        assert secret not in clean
    assert "2026-10" in clean
    SEC.install_log_scrubbing()
    lg = logging.getLogger("uvicorn.access")
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        lg.info("GET /x?pan=%s", "PQRST5678K")
    assert "PQRST5678K" not in caplog.text and "[PAN]" in caplog.text


def test_security_headers_and_no_store():
    r = TestClient(app).get("/api/auth/me")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- config & migration
def test_migration_is_idempotent():
    from app import migrate
    assert migrate.run(engine) == []


def test_production_refuses_default_secrets():
    env = {**os.environ, "FINORA_ENV": "production", "PAN_PEPPER": "finora-local-pepper-change-me", "COOKIE_SECURE": "true"}
    r = subprocess.run([sys.executable, "-c", "import app.config"], env=env, capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))
    assert r.returncode != 0 and "PAN_PEPPER" in r.stderr
    env.update(PAN_PEPPER="x" * 40, COOKIE_SECURE="false")
    r = subprocess.run([sys.executable, "-c", "import app.config"], env=env, capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))
    assert r.returncode != 0 and "COOKIE_SECURE" in r.stderr

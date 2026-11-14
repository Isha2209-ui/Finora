"""Demo sandboxes: faithful copy, isolation, reset, expiry - and the templates never change."""
import hashlib
import io
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import models as M
from app.database import SessionLocal
from app.services import sandbox
from app.services.profile_ops import PROFILE_TABLES

from .conftest import DEMO, signed_in_client

SOURCE_TABLES = [m for m in PROFILE_TABLES if m not in (M.AnalysisResult, M.Recommendation, M.Report, M.ChatMessage)]


def fingerprint(internal_id: str) -> dict:
    """Row counts per table + a hash of every transaction's (date, amount, type, category, description)."""
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == internal_id))
        fp = {m.__tablename__: db.scalar(select(func.count()).select_from(m).where(m.user_id == uid)) for m in SOURCE_TABLES}
        cards = [c for (c,) in db.execute(select(M.CreditCard.id).where(M.CreditCard.user_id == uid))]
        fp["card_statements"] = db.scalar(select(func.count()).select_from(M.CardStatement).where(M.CardStatement.card_id.in_(cards))) if cards else 0
        tx = db.execute(select(M.Transaction.date, M.Transaction.amount, M.Transaction.type, M.Transaction.category,
                               M.Transaction.raw_description).where(M.Transaction.user_id == uid)
                        .order_by(M.Transaction.date, M.Transaction.ref)).all()
        fp["tx_hash"] = hashlib.sha256(repr(tx).encode()).hexdigest()
        p = db.scalar(select(M.User).where(M.User.id == uid))
        fp["profile"] = (p.name, p.age, p.retirement_age_target, p.city)
        fp["balances"] = tuple(sorted(b for (b,) in db.execute(select(M.BankAccount.balance).where(M.BankAccount.user_id == uid))))
    return fp


TEMPLATES_BEFORE = {}


@pytest.fixture(scope="module", autouse=True)
def snapshot_templates():
    for uid in DEMO.values():
        TEMPLATES_BEFORE[uid] = fingerprint(uid)
    yield
    for uid in DEMO.values():                      # after every test in this module: originals untouched
        assert fingerprint(uid) == TEMPLATES_BEFORE[uid], f"template {uid} changed"


@pytest.fixture(scope="module")
def carol():
    return signed_in_client("carol")


@pytest.fixture(scope="module")
def dave():
    return signed_in_client("dave")


def explore(c, template="FINORA_USER_002"):
    r = c.post("/api/demo/explore", json={"template_id": template})
    assert r.status_code == 200, r.text
    return r.json()


def test_templates_listed_as_synthetic(carol):
    t = carol.get("/api/demo/templates").json()
    assert [x["template_id"] for x in t] == list(DEMO.values())
    assert all(x["synthetic"] and x["description"] and "****" in x["pan_masked"] for x in t)


def test_explore_creates_a_faithful_owned_expiring_copy(carol):
    r = explore(carol)
    p = r["profile"]
    assert r["created"] and p["kind"] == "sandbox" and not p["read_only"] and p["internal_id"].startswith("SB_")
    assert "synthetic" in r["notice"] and "no bank data was fetched" in r["notice"] and "24 hours" in r["notice"]
    exp = datetime.fromisoformat(p["expires_at"])
    assert timedelta(hours=23, minutes=59) < exp - datetime.utcnow() <= timedelta(hours=24)
    sb, tpl = fingerprint(p["internal_id"]), TEMPLATES_BEFORE["FINORA_USER_002"]
    assert sb == tpl                                                       # every source row copied, nothing else
    assert sb["transactions"] > 300 and sb["card_statements"] > 0


def test_sandbox_analysis_matches_the_template(carol, analyses):
    p = explore(carol)["profile"]["internal_id"]
    a, t = carol.get(f"/api/profiles/{p}/analysis").json(), analyses["FINORA_USER_002"]
    assert a["ml_errors"] == {}
    assert a["net_worth"]["net_worth"] == pytest.approx(t["net_worth"]["net_worth"], abs=1)
    assert a["health_score"]["score"] == pytest.approx(t["health_score"]["score"], abs=0.1)
    assert a["ml"]["credit_risk"]["overall_risk_band"] == t["ml"]["credit_risk"]["overall_risk_band"]
    assert a["ml"]["anomaly"]["flagged_count"] == t["ml"]["anomaly"]["flagged_count"]
    assert {r["code"] for r in a["recommendations"]} == {r["code"] for r in t["recommendations"]}


def test_explore_again_reuses_the_same_sandbox(carol):
    a, b = explore(carol), explore(carol)
    assert not b["created"] and a["profile"]["internal_id"] == b["profile"]["internal_id"]
    via_pan = carol.post("/api/lookup", json={"pan": "PQRST5678K"}).json()
    assert via_pan["profile"]["internal_id"] == a["profile"]["internal_id"] and "PQRST5678K" not in str(via_pan)


def test_every_edit_goes_to_the_sandbox_only(carol):
    p = explore(carol)["profile"]["internal_id"]
    tx = carol.get(f"/api/profiles/{p}/transactions", params={"limit": 2}).json()["items"]
    assert carol.patch(f"/api/profiles/{p}/transactions/{tx[0]['id']}", json={"category": "Travel"}).status_code == 200
    assert carol.delete(f"/api/profiles/{p}/transactions/{tx[1]['id']}").status_code == 200
    assert carol.post(f"/api/profiles/{p}/transactions", json={"date": "2026-10-30", "amount": 999, "description": "UPI/DR/1/UBER/AXIS/uber@okaxis"}).status_code == 200
    csv = b"Date,Narration,Withdrawal,Deposit\n29/10/2026,UPI/DR/123456789012/BIGBASKET/ICIC/bigbasket@ybl/Payment,1234,\n"
    up = carol.post(f"/api/profiles/{p}/upload", files={"file": ("s.csv", io.BytesIO(csv), "text/csv")})
    assert up.status_code == 200 and up.json()["transactions_added"] == 1
    assert carol.patch(f"/api/profiles/{p}", json={"age": 45, "retirement_age_target": 50}).status_code == 200
    rec = carol.get(f"/api/profiles/{p}/recommendations").json()[0]
    assert carol.patch(f"/api/profiles/{p}/recommendations/{rec['id']}", json={"status": "accepted"}).json()["status"] == "accepted"
    assert fingerprint(p) != TEMPLATES_BEFORE["FINORA_USER_002"]
    assert fingerprint("FINORA_USER_002") == TEMPLATES_BEFORE["FINORA_USER_002"]


def test_other_accounts_cannot_see_the_sandbox(carol, dave):
    mine = explore(carol)["profile"]["internal_id"]
    assert dave.get(f"/api/profiles/{mine}").status_code == 404
    assert dave.get(f"/api/profiles/{mine}/transactions").status_code == 404
    assert dave.post(f"/api/profiles/{mine}/reset").status_code == 404
    assert mine not in {p["internal_id"] for p in dave.get("/api/profiles").json()}
    theirs = explore(dave)["profile"]["internal_id"]
    assert theirs != mine and fingerprint(theirs) == TEMPLATES_BEFORE["FINORA_USER_002"]


def test_reset_restores_the_original(carol):
    p = explore(carol)["profile"]["internal_id"]
    carol.patch(f"/api/profiles/{p}", json={"age": 60})
    assert fingerprint(p) != TEMPLATES_BEFORE["FINORA_USER_002"]
    r = carol.post(f"/api/profiles/{p}/reset")
    assert r.status_code == 200 and r.json()["profile"]["internal_id"] == p             # same ID, fresh copy
    assert fingerprint(p) == TEMPLATES_BEFORE["FINORA_USER_002"]
    assert carol.get(f"/api/profiles/{p}").json()["age"] == TEMPLATES_BEFORE["FINORA_USER_002"]["profile"][1]
    assert all(r["status"] == "open" for r in carol.get(f"/api/profiles/{p}/recommendations").json())


def test_only_sandboxes_can_be_reset(carol):
    own = carol.post("/api/profiles", json={"name": "Carol Own", "age": 33, "monthly_income": 70000}).json()["profile"]["internal_id"]
    assert carol.post(f"/api/profiles/{own}/reset").status_code == 422
    assert carol.post("/api/profiles/FINORA_USER_001/reset").status_code == 403


def test_expired_sandbox_is_unreachable_then_purged(dave):
    p = explore(dave, "FINORA_USER_004")["profile"]["internal_id"]
    with SessionLocal() as db:
        sb = db.scalar(select(M.User).where(M.User.internal_id == p))
        sb.expires_at = datetime.utcnow() - timedelta(minutes=1)
        sb_id = sb.id
        db.commit()
    assert dave.get(f"/api/profiles/{p}").status_code == 404
    with SessionLocal() as db:
        assert sandbox.purge_expired(db) >= 1
        assert db.get(M.User, sb_id) is None
        assert db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.user_id == sb_id)) == 0
    fresh = explore(dave, "FINORA_USER_004")
    assert fresh["created"] and fresh["profile"]["internal_id"] != p


def test_lookup_never_fetches_real_data(carol):
    r = carol.post("/api/lookup", json={"pan": "AAAPL1234C"})          # valid format, not a demo identifier
    assert r.status_code == 404 and "cannot fetch real financial data" in r.json()["detail"]
    assert "AAAPL1234C" not in r.text


def test_sandbox_can_be_deleted_by_its_owner(dave):
    p = explore(dave, "FINORA_USER_003")["profile"]["internal_id"]
    assert dave.delete(f"/api/profiles/{p}").status_code == 200
    assert dave.get(f"/api/profiles/{p}").status_code == 404

"""Release blockers from the second independent audit (A-F) plus test isolation. Each test reproduces the auditor's
scenario and checks money figures (income, expenses, balances, net worth), not just stored row counts."""
import io
import threading
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app import config
from app import models as M
from app.database import SessionLocal
from app.services import statement_import as SI

from . import statement_fixtures as F
from .conftest import DEV_DB_PATH, TEST_DB_PATH, signed_in_client
from .test_statement_fixes import _csv
from .test_statement_import import _import, _profile


def _cf(c, pid):
    return c.get(f"/api/profiles/{pid}/analysis").json()["cash_flow"]


def _rows(n_months=4, salary=90000):
    rows = []
    for m in range(1, n_months + 1):
        rows += [(f"01/{m:02d}/2026", "NEFT CR-HDFC0000123-ACME CORP-SALARY", None, salary),
                 (f"05/{m:02d}/2026", "UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment", 450, None),
                 (f"09/{m:02d}/2026", "UPI/DR/402918371111/BIGBASKET/ICIC/bigbasket@ybl/Payment", 3000, None),
                 (f"14/{m:02d}/2026", "IMPS/P2A/412345678901/RENT FLAT", 25000, None)]
    return rows


def _preview(c, pid, content, name):
    r = c.post(f"/api/profiles/{pid}/imports", files={"file": (name, io.BytesIO(content), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


def _start(c, pid, imp_id, **body):
    return c.post(f"/api/profiles/{pid}/imports/{imp_id}/start", json=body)


# ---------------------------------------------------------------- isolation
def test_suite_runs_on_a_temporary_copy_never_the_dev_database():
    assert str(TEST_DB_PATH) in config.DATABASE_URL and str(DEV_DB_PATH) not in config.DATABASE_URL
    assert str(config.IMPORT_TMP_DIR).startswith(str(TEST_DB_PATH.parent)) and str(config.REPORTS_DIR).startswith(str(TEST_DB_PATH.parent))


# ---------------------------------------------------------------- A: stale previews, concurrency, partial overlap, look-alikes
def test_a_previews_taken_before_an_import_cannot_double_count():
    c = signed_in_client("a1")
    pid, hdfc, sbi, _ = _profile(c)
    full = _csv(_rows())
    cut = _csv([(d, n[:30], dr, cr) for d, n, dr, cr in _rows()])
    p1, p2, p3 = _preview(c, pid, full, "f1.csv"), _preview(c, pid, cut, "f2.csv"), _preview(c, pid, full, "f3.csv")
    assert _start(c, pid, p1["id"], account_id=hdfc).status_code == 202
    base = _cf(c, pid)
    for p, body in ((p2, {"account_id": sbi}), (p3, {"new_account": {"bank_name": "Axis", "last4": "3131", "balance": 1000}, "allow_same_file": True})):
        assert _start(c, pid, p["id"], **body).status_code == 202          # preview was stale, so the route let it through
        s = c.get(f"/api/profiles/{pid}/imports/{p['id']}").json()["summary"]
        assert s["transactions_added"] == 0 and s["income_records_added"] == 0 and s["already_on_other_accounts"] == 16
    after = _cf(c, pid)
    assert after["avg_monthly_income"] == base["avg_monthly_income"] == 90000
    assert after["avg_monthly_expenses"] == base["avg_monthly_expenses"]


def test_a_two_imports_started_at_the_same_time_are_serialised():
    c = signed_in_client("a2")
    pid, hdfc, sbi, _ = _profile(c)
    full = _csv(_rows())
    p1, p2 = _preview(c, pid, full, "x.csv"), _preview(c, pid, full, "y.csv")
    with SessionLocal() as db:
        user = db.scalar(select(M.User).where(M.User.internal_id == pid))
        SI.configure(db, user, db.get(M.StatementImport, p1["id"]), {"account_id": hdfc})
        SI.configure(db, user, db.get(M.StatementImport, p2["id"]), {"account_id": sbi})
    ts = [threading.Thread(target=SI.run, args=(i,)) for i in (p1["id"], p2["id"])]
    [t.start() for t in ts]
    [t.join() for t in ts]
    sums = [c.get(f"/api/profiles/{pid}/imports/{i}").json()["summary"] for i in (p1["id"], p2["id"])]
    assert sorted(s["income_records_added"] for s in sums) == [0, 4]
    assert _cf(c, pid)["avg_monthly_income"] == 90000


def test_a_partial_overlap_below_half_is_not_imported_twice():
    c = signed_in_client("a3")
    pid, hdfc, sbi, _ = _profile(c)
    rows = _rows(n_months=6)                                        # 24 rows
    _import(c, pid, _csv(rows[:8]), "first.csv", account_id=hdfc)    # 8 of them (2 salaries) already on HDFC
    pv = _preview(c, pid, _csv(rows), "all.csv")
    assert pv["detection"]["overlap"][0]["share_pct"] < 50
    _start(c, pid, pv["id"], account_id=sbi)
    s = c.get(f"/api/profiles/{pid}/imports/{pv['id']}").json()["summary"]
    assert s["already_on_other_accounts"] == 8 and s["income_records_added"] == 4
    assert c.get(f"/api/profiles/{pid}/insights").json()["income"]["total"] == 6 * 90000      # not 8 x 90,000


@pytest.mark.parametrize("variant", ["prefix", "cut11"])
def test_a_reformatted_narrations_are_recognised_as_the_same_rows(variant):
    c = signed_in_client("a4")
    pid, hdfc, *_ = _profile(c)
    _import(c, pid, _csv(_rows()), "one.csv", account_id=hdfc)
    base = _cf(c, pid)
    alt = [(d, ("TXN " + n) if variant == "prefix" else n[:11], dr, cr) for d, n, dr, cr in _rows()]
    _, s = _import(c, pid, _csv(alt), "two.csv", account_id=hdfc)
    assert s["summary"]["transactions_added"] == 0 and s["summary"]["income_records_added"] == 0
    assert _cf(c, pid)["avg_monthly_income"] == base["avg_monthly_income"] == 90000


# ---------------------------------------------------------------- B: unrecognised credits are not transfer evidence; 1:1
def test_b_unsure_debits_never_pair_with_an_unrecognised_credit():
    c = signed_in_client("b1")
    pid, hdfc, sbi, _ = _profile(c)
    _import(c, pid, _csv([("05/07/2026", "UPI/CR/5555/RAHUL SHARMA/okaxis/dinner", None, 600)]), "sbi.csv", account_id=sbi)
    debits = [("05/07/2026", "UPI/DR/31313131/SRI BALAJI STORES/okhdfc/Pay", 600, None),
              ("05/07/2026", "UPI/DR/42424242/MANOJ KUMAR/oksbi/sent", 600, None),
              ("05/07/2026", "POS 4521XXXXXXXX1111 SRI LAKSHMI ENTERPRISES", 600, None),
              ("06/07/2026", "NEFT DR-SBIN0001234-ANITA GIFT", 600, None)]
    _, s = _import(c, pid, _csv(debits), "hdfc.csv", account_id=hdfc)
    assert s["summary"]["transfers"] == 0
    with SessionLocal() as db:
        txs = db.scalars(select(M.Transaction).where(M.Transaction.import_id == s["id"])).all()
    assert all(t.category != "Transfer" for t in txs) and any(t.confidence < 0.6 for t in txs)   # the unsure path was exercised
    assert _cf(c, pid)["avg_monthly_expenses"] == pytest.approx(2400, abs=0.01)


def test_b_one_recognised_transfer_pairs_with_at_most_one_row():
    c = signed_in_client("b2")
    pid, hdfc, sbi, _ = _profile(c)
    _import(c, pid, _csv([("08/07/2026", "NEFT CR-OWN ACCOUNT TRF-XX1234", None, 5000)]), "out.csv", account_id=sbi)
    _, s = _import(c, pid, _csv([("08/07/2026", "UPI/DR/31313131/SRI BALAJI STORES/okhdfc/Pay", 5000, None),
                                 ("08/07/2026", "UPI/DR/42424242/MANOJ KUMAR/oksbi/sent", 5000, None)]), "hdfc.csv", account_id=hdfc)
    with SessionLocal() as db:
        cats = [t.category_source for t in db.scalars(select(M.Transaction).where(M.Transaction.import_id == s["id"]))]
    assert cats.count("rule:matched_own_account_transfer") <= 1


# ---------------------------------------------------------------- C: no balance from an undone statement survives
def test_c_created_account_does_not_keep_an_undone_statements_balance():
    c = signed_in_client("c")
    pid = c.post("/api/profiles", json={"name": "Cee Tester", "age": 30}).json()["profile"]["internal_id"]
    base_nw = c.get(f"/api/profiles/{pid}/analysis").json()["net_worth"]["net_worth"]
    _, a = _import(c, pid, _csv([("01/02/2026", "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment", 200, None),
                                 ("09/02/2026", "UPI/DR/2/UBER/AXIS/uber@okaxis/Payment", 200, None)], opening=0),
                   "a.csv", new_account={"bank_name": "Kotak", "last4": "8080"})
    acc = a["account_id"]
    _, b = _import(c, pid, _csv([("01/03/2026", "NEFT CR-ACME CORP-SALARY", None, 101000),
                                 ("09/03/2026", "UPI/DR/3/ZOMATO/HDFC/zomato@ybl", 400, None)], opening=-400), "b.csv", account_id=acc)
    assert b["summary"]["balance"]["applied"]                              # statement-sourced and newer: refreshed
    c.delete(f"/api/profiles/{pid}/imports/{a['id']}")
    c.delete(f"/api/profiles/{pid}/imports/{b['id']}")
    with SessionLocal() as db:
        assert db.get(M.BankAccount, acc) is None                          # nothing of either statement is left
    assert c.get(f"/api/profiles/{pid}/analysis").json()["net_worth"]["net_worth"] == base_nw


# ---------------------------------------------------------------- D: undo never deletes an account it did not create
def test_d_undo_cannot_delete_another_users_account_with_a_reused_id():
    u1, u2 = signed_in_client("d1"), signed_in_client("d2")
    p1 = u1.post("/api/profiles", json={"name": "Dee One", "age": 30}).json()["profile"]["internal_id"]
    p2 = u2.post("/api/profiles", json={"name": "Dee Two", "age": 30}).json()["profile"]["internal_id"]
    _, imp = _import(u1, p1, _csv([("05/09/2026", "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment", 500, None)]),
                     new_account={"bank_name": "Axis", "last4": "5151", "balance": 10000})
    acc = imp["account_id"]
    assert u1.delete(f"/api/profiles/{p1}/records/bank_accounts/{acc}?cascade=true").status_code == 200
    other = u2.post(f"/api/profiles/{p2}/records/bank_accounts", json={"bank_name": "Axis", "last4": "5151", "balance": 777777}).json()
    mine = u1.post(f"/api/profiles/{p1}/records/bank_accounts", json={"bank_name": "Axis", "last4": "5151", "balance": 5}).json()
    u = u1.delete(f"/api/profiles/{p1}/imports/{imp['id']}").json()
    assert u["undo"]["account_removed"] is False
    with SessionLocal() as db:
        assert db.get(M.BankAccount, other["id"]).balance == 777777 and db.get(M.BankAccount, mine["id"]) is not None
    assert u2.get(f"/api/profiles/{p2}/analysis").json()["net_worth"]["net_worth"] == 777777


# ---------------------------------------------------------------- E: uploads limited before the body is read
def test_e_chunked_uploads_are_refused_before_reading(monkeypatch):
    import app.routes.statements as R
    monkeypatch.setattr(R, "read_limited", lambda *a, **k: pytest.fail("the endpoint read the body"))
    c = signed_in_client("e")
    pid, *_ = _profile(c)
    sent = {"n": 0}

    def body():
        for _ in range(50):
            sent["n"] += 1
            yield b"x" * 1_000_000
    r = c.post(f"/api/profiles/{pid}/imports", content=body(), headers={"Content-Type": "multipart/form-data; boundary=zz"})
    assert r.status_code == 411
    anon = httpx.Client(transport=c._transport, base_url="http://testserver")
    r = anon.post(f"/api/profiles/{pid}/imports", content=b"x" * 3_000_000, headers={"Content-Type": "multipart/form-data; boundary=zz"})
    assert r.status_code == 401
    r = c.post(f"/api/profiles/{pid}/imports", content=b"x" * 10, headers={"Content-Type": "multipart/form-data; boundary=zz",
                                                                        "Content-Length": str(100_000_000)})
    assert r.status_code == 413
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        assert not db.scalar(select(func.count()).select_from(M.StatementImport).where(M.StatementImport.user_id == uid))


# ---------------------------------------------------------------- F: several server processes on one database
def test_f_recovery_leaves_another_processes_live_import_alone():
    c = signed_in_client("f1")
    pid, hdfc, *_ = _profile(c)
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        live = M.StatementImport(user_id=uid, filename="live.csv", sha256="2" * 64, size_bytes=1, status="running",
                                 heartbeat_at=datetime.utcnow(), progress_pct=42.0)
        dead = M.StatementImport(user_id=uid, filename="dead.csv", sha256="3" * 64, size_bytes=1, status="running",
                                 heartbeat_at=datetime.utcnow() - timedelta(seconds=SI.STALE_AFTER + 60))
        undone = M.StatementImport(user_id=uid, filename="undone.csv", sha256="4" * 64, size_bytes=1, status="undone", summary={"x": 1})
        db.add_all([live, dead, undone])
        db.flush()
        db.add(M.Transaction(user_id=uid, ref="live1", date=datetime(2026, 1, 5).date(), amount=10, raw_description="half", import_id=live.id))
        db.commit()
        ids = live.id, dead.id, undone.id
        SI.recover_interrupted(db)                                       # what a newly started process does
        assert db.get(M.StatementImport, ids[0]).status == "running"
        assert db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.import_id == ids[0])) == 1
        assert db.get(M.StatementImport, ids[1]).status == "failed"
        assert db.get(M.StatementImport, ids[2]).status == "undone"
    st = c.get(f"/api/profiles/{pid}/imports/{ids[0]}").json()
    assert st["pct"] == 42.0                                             # progress visible from any process
    assert _start(c, pid, _preview(c, pid, F.hdfc(F.bank_rows()[:10]), "z.csv")["id"], account_id=hdfc).status_code == 409


def test_f_cancel_reaches_the_process_that_runs_the_import():
    c = signed_in_client("f2")
    pid, hdfc, *_ = _profile(c)
    pv = _preview(c, pid, F.hdfc(F.bank_rows()), "s.csv")
    with SessionLocal() as db:
        user = db.scalar(select(M.User).where(M.User.internal_id == pid))
        imp = db.get(M.StatementImport, pv["id"])
        SI.configure(db, user, imp, {"account_id": hdfc, "update_balance": True})
        imp.cancel_requested = True                                      # set by the API in a DIFFERENT process
        db.commit()
    SI.CANCEL.discard(pv["id"])
    SI.run(pv["id"])
    st = c.get(f"/api/profiles/{pid}/imports/{pv['id']}").json()
    assert st["status"] == "cancelled"
    with SessionLocal() as db:
        assert not db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.import_id == pv["id"]))
        assert db.get(M.BankAccount, hdfc).balance == 50000

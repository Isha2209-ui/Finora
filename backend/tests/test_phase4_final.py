"""Phase 4 closure checks: immutable account identity for undo, and one server process per database."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app import models as M
from app import process_lock
from app.database import SessionLocal

from .conftest import TEST_DB_PATH, signed_in_client
from .test_statement_fixes import _csv
from .test_statement_import import _import

BACKEND = Path(__file__).resolve().parents[1]
ROW = [("05/09/2026", "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment", 500, None)]


def _new_profile(c, name):
    return c.post("/api/profiles", json={"name": name, "age": 30}).json()["profile"]["internal_id"]


def test_undo_never_deletes_another_users_account_even_with_the_same_id_and_name():
    u1, u2 = signed_in_client("uid1"), signed_in_client("uid2")
    p1, p2 = _new_profile(u1, "Owner One"), _new_profile(u2, "Owner Two")
    _, imp = _import(u1, p1, _csv(ROW), new_account={"bank_name": "Axis", "last4": "5151", "balance": 10000})
    created = imp["account_id"]
    with SessionLocal() as db:                       # removed WITHOUT the My Data path, so only the uid can protect
        db.execute(delete(M.Transaction).where(M.Transaction.account_id == created))
        db.execute(delete(M.BankAccount).where(M.BankAccount.id == created))
        db.commit()
    other = u2.post(f"/api/profiles/{p2}/records/bank_accounts",
                    json={"bank_name": "Axis", "last4": "5151", "balance": 777777}).json()
    assert other["id"] == created                    # SQLite really reused the id: the dangerous case is exercised
    undo = u1.delete(f"/api/profiles/{p1}/imports/{imp['id']}").json()["undo"]
    assert undo["account_removed"] is False
    with SessionLocal() as db:
        acc = db.get(M.BankAccount, other["id"])
        assert acc is not None and acc.balance == 777777 and acc.user_id != db.scalar(
            select(M.User.id).where(M.User.internal_id == p1))
    assert u2.get(f"/api/profiles/{p2}/analysis").json()["net_worth"]["net_worth"] == 777777


def test_undo_still_removes_the_account_it_really_created():
    c = signed_in_client("uid3")
    pid = _new_profile(c, "Owner Three")
    _, imp = _import(c, pid, _csv(ROW), new_account={"bank_name": "Axis", "last4": "6161", "balance": 2500})
    with SessionLocal() as db:
        assert db.get(M.BankAccount, imp["account_id"]).uid == imp["summary"]["created_account_uid"]
    assert c.delete(f"/api/profiles/{pid}/imports/{imp['id']}").json()["undo"]["account_removed"] is True
    assert c.get(f"/api/profiles/{pid}/analysis").json()["net_worth"]["net_worth"] == 0


def test_a_second_process_cannot_take_the_same_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'x.db'}"
    child = subprocess.Popen([sys.executable, "-c", "import sys,time; from app import process_lock as L; L.acquire(sys.argv[1]); "
                              "print('locked', flush=True); time.sleep(60)", url], cwd=BACKEND, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(process_lock.SecondProcessError):
            process_lock.acquire(url)
    finally:
        child.kill()
        child.wait()
    assert process_lock.acquire(url) is not None                # released by the OS when the holder died
    process_lock.release_all()


def _wait(port, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            return urllib.request.urlopen(f"http://127.0.0.1:{port}/docs", timeout=1).status
        except OSError:
            time.sleep(0.5)
    return None


def test_a_second_real_server_on_the_same_database_refuses_to_start():
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{TEST_DB_PATH}"}
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port"]
    first = subprocess.Popen(cmd + ["8011"], cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert _wait(8011) == 200
        second = subprocess.run(cmd + ["8012"], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=90)
        assert second.returncode != 0 and "Another Finora server process is already using" in second.stderr
        assert _wait(8011, 5) == 200                             # the first server is unaffected
    finally:
        first.terminate()
        first.wait(30)

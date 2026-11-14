"""Regression tests for the defects found by the independent Phase 4 audit (C1-C7 and the minor findings).

Every test checks money figures (totals, balances, net worth, income) as the analysis reports them - not only how many
rows were stored. Statements are synthetic (tests/statement_fixtures.py).
"""
import io

import pytest
from sqlalchemy import func, select

from app import models as M
from app.database import SessionLocal
from app.services import statement_import as SI

from . import statement_fixtures as F
from .conftest import signed_in_client
from .test_statement_import import BANK, _import, _profile

HEAD = "Date,Narration,Withdrawal,Deposit,Balance\n"


def _csv(rows, opening=100000.0):
    """rows: (dd/mm/yyyy, narration, debit, credit). Running balance computed in order."""
    out, bal = [HEAD], opening
    for d, n, dr, cr in rows:
        bal += (cr or 0) - (dr or 0)
        out.append(f'{d},"{n}",{dr or ""},{cr or ""},{bal:.2f}\n')
    return "".join(out).encode()


def _analysis(c, pid):
    return c.get(f"/api/profiles/{pid}/analysis").json()


def _acct(acc_id):
    with SessionLocal() as db:
        a = db.get(M.BankAccount, acc_id)
        return a.balance, a.balance_source, a.balance_as_of


# ---------------------------------------------------------------- C1: genuine repeats count in every figure
def test_c1_identical_same_day_rows_are_counted_in_totals():
    c = signed_in_client("c1")
    pid, acc, *_ = _profile(c)
    rows = []
    for m in ("07", "08", "09", "10"):
        rows += [(f"01/{m}/2026", "NEFT CR-HDFC0000123-ACME CORP-SALARY", None, 60000),
                 (f"05/{m}/2026", "UPI/DR/1111/DMRC/YESB/dmrc@ybl/Payment", 200, None),
                 (f"05/{m}/2026", "UPI/DR/1111/DMRC/YESB/dmrc@ybl/Payment", 200, None),      # same metro recharge twice
                 (f"10/{m}/2026", "UPI/DR/2222/BIGBASKET/ICIC/bigbasket@ybl/Payment", 3000, None)]
    _, s = _import(c, pid, _csv(rows), account_id=acc)
    assert s["summary"]["transactions_added"] == 12
    i = c.get(f"/api/profiles/{pid}/insights").json()
    travel = next(x for x in i["where"]["categories"] if x["category"] == "Travel")
    assert travel["total"] == 1600                                       # 2 x 200 x 4 months, not 800
    assert _analysis(c, pid)["cash_flow"]["avg_monthly_expenses"] == pytest.approx(3400, abs=0.01)


# ---------------------------------------------------------------- C2: overlaps never double count
def test_c2_overlap_with_shortened_narrations_adds_nothing_and_income_is_unchanged():
    c = signed_in_client("c2a")
    pid, acc, *_ = _profile(c)
    part = BANK[:60]
    _import(c, pid, F.hdfc(part), account_id=acc)
    before = _analysis(c, pid)["cash_flow"]
    cut = [F.Row(r.date, r.desc[:30], r.amount, r.type, r.truth, r.balance) for r in part]       # an export that truncates text
    _, s = _import(c, pid, F.hdfc(cut), "cut.csv", account_id=acc)
    assert s["summary"]["transactions_added"] == 0 and s["summary"]["income_records_added"] == 0
    assert s["summary"]["duplicates_skipped"] == len(part) and s["summary"]["duplicates_near"] > 0
    after = _analysis(c, pid)["cash_flow"]
    assert after["avg_monthly_income"] == before["avg_monthly_income"] and after["avg_monthly_expenses"] == before["avg_monthly_expenses"]


def test_c2_same_statement_on_another_account_needs_confirmation():
    c = signed_in_client("c2b")
    pid, acc, other, _ = _profile(c)
    _import(c, pid, F.hdfc(BANK[:60]), account_id=acc)
    income = _analysis(c, pid)["cash_flow"]["avg_monthly_income"]
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("again.csv", io.BytesIO(F.icici(BANK[:60])), "text/csv")}).json()
    assert pv["detection"]["overlap"][0]["id"] == acc and pv["detection"]["overlap"][0]["share_pct"] == 100.0
    r = c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": other})
    assert r.status_code == 409 and "already recorded" in r.json()["detail"]
    r = c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"new_account": {"bank_name": "Axis", "last4": "9999", "balance": 1}})
    assert r.status_code == 409
    assert _analysis(c, pid)["cash_flow"]["avg_monthly_income"] == income            # nothing was double counted
    # attaching it to the right account is allowed and adds nothing
    c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": acc})
    s = c.get(f"/api/profiles/{pid}/imports/{pv['id']}").json()["summary"]
    assert s["transactions_added"] == 0 and s["income_records_added"] == 0


def test_c2_imported_look_alike_is_flagged():
    c = signed_in_client("c2c")
    pid, acc, *_ = _profile(c)
    _import(c, pid, _csv([("05/10/2026", "POS 4521XXXXXXXX1111 CROMA PUNE", 2500, None)]), account_id=acc)
    _, s = _import(c, pid, _csv([("05/10/2026", "CROMA RETAIL ONLINE PAYMENT 88812", 2500, None)]), "b.csv", account_id=acc)
    assert s["summary"]["transactions_added"] == 1 and s["summary"]["possible_duplicates"] == 1
    reasons = [it["reason"] for g in c.get(f"/api/profiles/{pid}/review").json()["groups"] for it in g["items"]]
    assert any("another statement" in (x or "") for x in reasons)


# ---------------------------------------------------------------- C3: amount + date alone never make a transfer
def test_c3_unrelated_equal_amounts_do_not_become_transfers():
    c = signed_in_client("c3")
    pid, acc, other, _ = _profile(c)
    # a friend's Rs 600 arrives in the SBI account (unrecognised credit -> held as transfer)
    _import(c, pid, _csv([("05/07/2026", "UPI/CR/5555/RAHUL SHARMA/okaxis/dinner", None, 600)]), "sbi.csv", account_id=other)
    # the same day a Rs 600 Swiggy order leaves the HDFC account
    _, s = _import(c, pid, _csv([("05/07/2026", "UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment", 600, None)]), "hdfc.csv",
                   account_id=acc)
    assert s["summary"]["transfers"] == 0 and s["summary"]["spend_by_category"] == {"Dining": 600.0}
    assert _analysis(c, pid)["cash_flow"]["avg_monthly_expenses"] == pytest.approx(600, abs=0.01)
    # a genuine own transfer (generic narration, other side already a transfer) is still paired
    _import(c, pid, _csv([("08/07/2026", "IMPS/P2A/777/SELF TRANSFER", 5000, None)]), "out.csv", account_id=other)
    _, s2 = _import(c, pid, _csv([("08/07/2026", "IMPS/P2A/777/ADITYA K", None, 5000)]), "in.csv", account_id=acc)
    assert s2["summary"]["transfers"] == 1 and s2["summary"]["income_records_added"] == 0


# ---------------------------------------------------------------- C4: cancel / crash never leave a half import
def test_c4_cancel_during_analysis_keeps_a_complete_undoable_import(monkeypatch):
    c = signed_in_client("c4a")
    pid, acc, *_ = _profile(c)
    real = SI._progress

    def cancel_late(i, st, d=0, n=0):
        if st == "analysis":
            SI.CANCEL.add(i)                                             # the person presses Cancel at 97%
        return real(i, st, d, n)
    monkeypatch.setattr(SI, "_progress", cancel_late)
    _, s = _import(c, pid, F.hdfc(BANK), account_id=acc, update_balance=True)
    assert s["status"] == "done"
    assert _acct(acc)[0] == BANK[-1].balance
    nw = _analysis(c, pid)["net_worth"]["net_worth"]
    assert nw == pytest.approx(BANK[-1].balance + 80000 - 12000, abs=0.01)   # analysis matches the stored rows and balance
    u = c.delete(f"/api/profiles/{pid}/imports/{s['id']}").json()
    assert u["undo"]["balance_restored"] and _acct(acc)[:2] == (50000, "manual")
    assert _analysis(c, pid)["net_worth"]["net_worth"] == pytest.approx(50000 + 80000 - 12000, abs=0.01)


def test_c4_cancel_after_save_is_refused_with_undo_advice():
    c = signed_in_client("c4b")
    pid, acc, *_ = _profile(c)
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        imp = M.StatementImport(user_id=uid, filename="x.csv", sha256="1" * 64, size_bytes=1, status="running", stage="analysis",
                                summary={"balance": {}})
        db.add(imp)
        db.commit()
        iid = imp.id
    r = c.post(f"/api/profiles/{pid}/imports/{iid}/cancel")
    assert r.status_code == 409 and "Undo" in r.json()["detail"]


def test_c4_crash_before_commit_leaves_balance_rows_account_and_file_untouched(monkeypatch):
    c = signed_in_client("c4c")
    pid, acc, *_ = _profile(c)
    real = SI._progress

    def crash(i, st, d=0, n=0):
        real(i, st, d, n)
        if st == "saving" and d >= 2000:
            raise KeyboardInterrupt                                      # stands in for the process dying mid-save
    monkeypatch.setattr(SI, "_progress", crash)
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("s.csv", io.BytesIO(F.big_bank(5000)[0]), "text/csv")}).json()
    SI.configure(*_ctx(pid, pv["id"]), {"account_id": None, "new_account": {"bank_name": "Axis", "last4": "4444", "balance": 7}})
    with pytest.raises(KeyboardInterrupt):
        SI.run(pv["id"])
    with SessionLocal() as db:                                          # what a killed server leaves behind
        imp = db.get(M.StatementImport, pv["id"])
        assert imp.status == "running" and db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.import_id == imp.id))
        SI.pending_path(imp.id).write_bytes(b"left over")
        _abandon(db, imp)                                               # the dead process stopped beating long ago
        SI.recover_interrupted(db)
        imp = db.get(M.StatementImport, pv["id"])
        assert imp.status == "failed"
        assert not db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.import_id == imp.id))
        assert not db.scalar(select(func.count()).select_from(M.BankAccount).where(M.BankAccount.account_masked == "XXXX4444",
                                                                                     M.BankAccount.user_id == imp.user_id))
        assert not SI.pending_path(imp.id).exists()
    assert _acct(acc)[0] == 50000
    assert _analysis(c, pid)["cash_flow"]["spending_known"] is False


def test_c4_crash_after_commit_is_finished_not_half_undone():
    c = signed_in_client("c4d")
    pid, acc, *_ = _profile(c)
    _, s = _import(c, pid, F.hdfc(BANK[:40]), account_id=acc, update_balance=True)
    with SessionLocal() as db:                                          # simulate: killed while refreshing the analysis
        imp = db.get(M.StatementImport, s["id"])
        imp.status = "running"
        _abandon(db, imp)
        SI.recover_interrupted(db)
        assert db.get(M.StatementImport, s["id"]).status == "done"
    assert _acct(acc)[0] == BANK[39].balance
    assert c.delete(f"/api/profiles/{pid}/imports/{s['id']}").json()["undo"]["balance_restored"]
    assert _acct(acc)[0] == 50000


def _abandon(db, imp):
    """Make an import look like its process died more than STALE_AFTER seconds ago."""
    from datetime import datetime, timedelta
    imp.heartbeat_at = datetime.utcnow() - timedelta(seconds=SI.STALE_AFTER + 60)
    db.commit()
    SI.PROGRESS.pop(imp.id, None)


def _ctx(pid, imp_id):
    db = SessionLocal()
    user = db.scalar(select(M.User).where(M.User.internal_id == pid))
    return db, user, db.get(M.StatementImport, imp_id)


# ---------------------------------------------------------------- C5: undo touches only its own rows
def test_c5_undo_keeps_a_later_imports_income_and_the_account_it_uses():
    c = signed_in_client("c5")
    pid = c.post("/api/profiles", json={"name": "C5", "age": 30}).json()["profile"]["internal_id"]
    _, a = _import(c, pid, _csv([("05/09/2026", "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment", 500, None)]),
                   new_account={"bank_name": "Axis", "last4": "1212", "balance": 10000})
    new_id = a["account_id"]
    _, b = _import(c, pid, _csv([("01/10/2026", "NEFT CR-ACME CORP-SALARY", None, 100000),
                                 ("15/10/2026", "SB INT PD 15-10-2026", None, 500)]), "b.csv", account_id=new_id)
    assert b["summary"]["income_records_added"] == 2
    u = c.delete(f"/api/profiles/{pid}/imports/{a['id']}").json()["undo"]
    assert u["account_removed"] is False                                # import B still uses it
    cf = _analysis(c, pid)["cash_flow"]
    assert cf["income_known"] and c.get(f"/api/profiles/{pid}/insights").json()["income"]["total"] == 100500
    assert c.get(f"/api/profiles/{pid}/imports/{b['id']}").json()["status"] == "done"
    with SessionLocal() as db:
        assert db.get(M.BankAccount, new_id) is not None


# ---------------------------------------------------------------- C6 / C7: typed balances and undo order
def _two_statements():
    older = _csv([("10/03/2025", "UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment", 400, None),
                  ("26/04/2025", "UPI/DR/2/UBER/AXIS/uber@okaxis/Payment", 200, None)], opening=632115.59)
    newer = _csv([("10/09/2026", "UPI/DR/3/ZOMATO/HDFC/zomato@ybl", 300, None),
                  ("20/10/2026", "UPI/DR/4/BIGBASKET/ICIC/bigbasket@ybl/Payment", 1700, None)], opening=702000.0)
    return older, newer                                               # closing 631,515.59 and 700,000.00


def test_c6_typed_balance_is_never_replaced_without_explicit_consent():
    c = signed_in_client("c6")
    pid, acc, *_ = _profile(c)
    c.patch(f"/api/profiles/{pid}/records/bank_accounts/{acc}", json={"balance": 333333})
    older, _ = _two_statements()
    _, s = _import(c, pid, older, account_id=acc)                      # not asked
    assert not s["summary"]["balance"]["applied"] and "Kept the balance you entered" in s["summary"]["balance"]["reason"]
    assert _acct(acc)[:2] == (333333, "manual")
    assert _analysis(c, pid)["net_worth"]["net_worth"] == pytest.approx(333333 + 80000 - 12000, abs=0.01)
    c.delete(f"/api/profiles/{pid}/imports/{s['id']}")
    _, s2 = _import(c, pid, older, "again.csv", account_id=acc, update_balance=True, allow_same_file=True)   # explicitly chosen
    assert s2["summary"]["balance"]["applied"] and _acct(acc)[0] == pytest.approx(631515.59)


@pytest.mark.parametrize("undo_order", [("A", "B"), ("B", "A")])
def test_c7_any_undo_order_returns_the_typed_balance(undo_order):
    c = signed_in_client("c7")
    pid, acc, *_ = _profile(c)
    c.patch(f"/api/profiles/{pid}/records/bank_accounts/{acc}", json={"balance": 333333})
    older, newer = _two_statements()
    _, a = _import(c, pid, older, "a.csv", account_id=acc, update_balance=True)
    _, b = _import(c, pid, newer, "b.csv", account_id=acc)              # statement-sourced and newer: refreshed automatically
    assert _acct(acc)[0] == pytest.approx(700000)
    ids = {"A": a["id"], "B": b["id"]}
    first, second = undo_order
    c.delete(f"/api/profiles/{pid}/imports/{ids[first]}")
    if first == "A":
        assert _acct(acc)[0] == pytest.approx(700000)                    # B is still in force
    else:
        assert _acct(acc)[0] == pytest.approx(631515.59)                 # back to A's balance while A is still in force
    c.delete(f"/api/profiles/{pid}/imports/{ids[second]}")
    bal, src, as_of = _acct(acc)
    assert (bal, src, as_of) == (333333, "manual", None)
    assert _analysis(c, pid)["net_worth"]["net_worth"] == pytest.approx(333333 + 80000 - 12000, abs=0.01)


# ---------------------------------------------------------------- minor findings
def test_preview_shows_the_whole_files_closing_balance():
    content, closing = F.big_bank(3000)
    c = signed_in_client("pv")
    pid, *_ = _profile(c)
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("big.csv", io.BytesIO(content), "text/csv")}).json()
    assert pv["detection"]["balance"]["closing_balance"] == closing and pv["detection"]["rows_valid"] == 3000


def test_invalid_date_format_is_a_clear_error():
    c = signed_in_client("df")
    pid, acc, *_ = _profile(c)
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("s.csv", io.BytesIO(F.hdfc(BANK[:10])), "text/csv")}).json()
    r = c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": acc, "date_format": "%Q-nonsense"})
    assert r.status_code == 422 and "Unsupported date format" in r.json()["detail"]


def test_regular_credit_is_not_a_second_salary():
    c = signed_in_client("sal")
    pid, acc, *_ = _profile(c)
    _import(c, pid, F.hdfc(BANK), account_id=acc)                       # salary already recorded for these months
    rows = [(f"03/{m:02d}/2026", "NEFT CR-HDFC0000999-GLOBEX LTD-PAYOUT", None, 82000) for m in range(5, 10)]
    _, s = _import(c, pid, _csv(rows), "side.csv", account_id=acc)
    assert s["summary"]["income_by_source"] == {"Other income": 410000.0} and s["summary"]["needs_review"] == 5
    sal = c.get(f"/api/profiles/{pid}/insights").json()["income"]["salary"]
    assert all(ch["to"] <= 105000 for ch in sal["changes"])             # no fake "+68% raise"


def test_atm_withdrawals_are_not_recurring_commitments():
    c = signed_in_client("atm")
    pid, acc, *_ = _profile(c)
    _import(c, pid, F.hdfc(BANK), account_id=acc)
    items = c.get(f"/api/profiles/{pid}/insights").json()["recurring"]["items"]
    assert not any(i["category"] == "Cash" for i in items)
    assert next(i for i in items if i["category"] == "Rent")["kind"] == "bill"
    assert next(i for i in items if i["category"] == "Subscriptions")["kind"] == "subscription"


def test_oversized_upload_is_refused_before_the_body_is_read(monkeypatch):
    import app.routes.statements as R
    monkeypatch.setattr(R, "UPLOAD_MAX_BYTES", 1000)
    monkeypatch.setattr(R, "read_limited", lambda *a, **k: pytest.fail("the endpoint read the body"))
    c = signed_in_client("big413")
    pid, *_ = _profile(c)
    r = c.post(f"/api/profiles/{pid}/imports", files={"file": ("x.csv", io.BytesIO(b"x" * 1_200_000), "text/csv")})
    assert r.status_code == 413


def test_uploaded_files_are_deleted_with_the_profile_and_at_start_up():
    c = signed_in_client("files")
    pid, *_ = _profile(c)
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("s.csv", io.BytesIO(F.hdfc(BANK[:10])), "text/csv")}).json()
    assert SI.pending_path(pv["id"]).exists()
    assert c.delete(f"/api/profiles/{pid}").status_code == 200
    assert not SI.pending_path(pv["id"]).exists()
    orphan = SI.pending_path(987654321)
    orphan.write_bytes(b"orphan")
    with SessionLocal() as db:
        SI.recover_interrupted(db)
    assert not orphan.exists()


def test_history_keeps_the_label_it_was_imported_to():
    c = signed_in_client("label")
    pid, acc, *_ = _profile(c)
    _, s = _import(c, pid, F.hdfc(BANK[:10]), account_id=acc)
    assert s["summary"]["target_label"] == "HDFC Bank XXXX1234"

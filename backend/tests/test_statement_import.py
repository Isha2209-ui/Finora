"""Phase 4: statement import, classification, review and intelligence.

Statements here are synthetic (tests/statement_fixtures.py) with known ground truth, written in six layouts.
Each test checks real effects on the analysis, not just that an endpoint answered.
"""
import io
import time
from collections import Counter

import pytest
from sqlalchemy import func, select

from app import models as M
from app.database import SessionLocal
from app.services import statement_import as SI
from app.services import statement_parser as P

from . import statement_fixtures as F
from .conftest import signed_in_client

BANK = F.bank_rows()
CARD = F.card_rows()
DAYS = sorted({r.date for r in BANK})


# ---------------------------------------------------------------- helpers
def _profile(c, name="Import Person"):
    pid = c.post("/api/profiles", json={"name": name, "age": 32}).json()["profile"]["internal_id"]
    acc = c.post(f"/api/profiles/{pid}/records/bank_accounts",
                 json={"bank_name": "HDFC Bank", "account_type": "salary", "last4": "1234", "balance": 50000, "interest_rate": 3}).json()
    other = c.post(f"/api/profiles/{pid}/records/bank_accounts",
                   json={"bank_name": "SBI", "account_type": "savings", "last4": F.OTHER_ACCOUNT_LAST4, "balance": 80000}).json()
    card = c.post(f"/api/profiles/{pid}/records/credit_cards",
                  json={"issuer": "HDFC Bank", "card_name": "Millennia", "last4": F.OWN_CARD_LAST4, "credit_limit": 200000,
                        "outstanding": 12000, "min_due": 600, "due_day": 5}).json()
    return pid, acc["id"], other["id"], card["id"]


def _import(c, pid, content, name="s.csv", **start):
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": (name, io.BytesIO(content), "text/csv")})
    assert pv.status_code == 201, pv.text
    st = c.post(f"/api/profiles/{pid}/imports/{pv.json()['id']}/start", json=start)
    if st.status_code != 202:
        return pv.json(), st
    return pv.json(), c.get(f"/api/profiles/{pid}/imports/{pv.json()['id']}").json()


@pytest.fixture(scope="module")
def ivy():
    c = signed_in_client("ivy")
    c.pid, c.acc, c.other, c.card = _profile(c)
    c.before = c.get(f"/api/profiles/{c.pid}/analysis").json()
    c.bank_pv, c.bank = _import(c, c.pid, F.hdfc(BANK), "hdfc.csv", account_id=c.acc, update_balance=True)
    c.card_pv, c.cardimp = _import(c, c.pid, F.card_statement(CARD), "card.csv", statement_kind="card", card_id=c.card)
    c.after = c.get(f"/api/profiles/{c.pid}/analysis").json()
    return c


# ---------------------------------------------------------------- detection across layouts
@pytest.mark.parametrize("writer,layout,fmt,order", [
    (F.hdfc, "HDFC-style savings export", "%d/%m/%y", "oldest first"),
    (F.sbi_newest_first, "SBI-style savings export", "%d %b %Y", "newest first"),
    (F.icici, "ICICI-style savings export", "%d/%m/%Y", "oldest first"),
    (F.kotak_semicolon, "Kotak-style export (amount + Dr/Cr)", "%d-%m-%Y", "oldest first"),
    (F.generic_signed, "Generic statement layout", "%Y-%m-%d", "oldest first"),
])
def test_every_bank_layout_is_read_exactly(writer, layout, fmt, order):
    t = P.read_table(writer(BANK))
    p = P.parse(t, kind="bank")
    d = p.detection
    assert d["layout"] == layout and d["date_format"] == fmt and d["file_order"] == order
    assert d["rows_valid"] == len(BANK) and d["months_covered"] == 24
    assert sorted(zip(p.rows["date"].dt.date, p.rows["amount"].round(2), p.rows["type"])) == \
        sorted((r.date, round(r.amount, 2), r.type) for r in BANK)
    b = d["balance"]
    assert b["verified"] and b["reconciled_pct"] == 100.0 and b["closing_balance"] == BANK[-1].balance
    assert b["closing_date"] == BANK[-1].date.isoformat()


def test_card_statement_layout_with_cr_marks():
    d = P.detect(F.card_statement(CARD))
    assert d["suggested_kind"] == "card" and d["layout_kind"] == "amount with Cr/Dr marks"
    p = P.parse(P.read_table(F.card_statement(CARD)), kind="card")
    assert p.detection["credits"] == sum(r.type == "credit" for r in CARD)            # payments & refunds are credits
    assert p.detection["balance"]["present"] is False


def test_encodings_delimiters_and_formats():
    rows = BANK[:40]
    utf16 = F.hdfc(rows).decode().encode("utf-16")
    cp = F.generic_signed(rows).decode().replace("Amount", "Amount (Rs.)").encode("cp1252")
    pipe = F.generic_signed(rows).decode().replace(",", "|").encode()
    for content in (utf16, cp, pipe):
        p = P.parse(P.read_table(content), kind="bank")
        assert p.detection["rows_valid"] == 40 and p.detection["balance"]["verified"]
    # "1,234.00 Dr" style, Indian grouping, parentheses and trailing minus
    v, mark = P.parse_amounts(__import__("pandas").Series(["1,23,456.78", "Rs. 500", "₹1,200", "(250.00)", "300-", "450.00 Cr", "75 DR", "", "abc"]))
    assert list(v.round(2).fillna(-9)) == [123456.78, 500, 1200, -250, -300, 450, 75, -9, -9]
    assert list(mark.fillna("")) == ["", "", "", "", "", "cr", "dr", "", ""]


def test_unquoted_thousands_separators_are_repaired_only_when_unambiguous():
    head = "Date,Narration,Withdrawal,Deposit,Balance\n"
    body = ("01/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,1,234.50,,98,765.50\n"      # 1,234.50 and 98,765.50 split
            "02/10/2026,NEFT CR SALARY ACME,,1,00,000.00,1,98,765.50\n"                     # Indian grouping
            "03/10/2026,POS AMAZON,500,,1,98,265.50\n")
    p = P.parse(P.read_table((head + body).encode()), kind="bank")
    assert list(p.rows["amount"]) == [1234.5, 100000.0, 500.0] and p.detection["balance"]["verified"]
    assert any("without quotes" in w for w in p.detection["warnings"])


# ---------------------------------------------------------------- full import into the pipeline
from app.ml import categoriser  # noqa: E402
BANK_SIDE = {"Rent", "EMI", "Cash", "Transfer", "Investment", "Card Payment"}       # rules, not ML (Phase 6, Option A)
def test_bank_import_classifies_against_ground_truth(ivy):
    s = ivy.bank["summary"]
    assert ivy.bank["status"] == "done" and ivy.bank["pct"] == 100.0
    salaries = [r for r in BANK if r.truth == "income:Salary"]
    interest = [r for r in BANK if r.truth == "income:Interest"]
    assert s["income_by_source"] == {"Salary": round(sum(r.amount for r in salaries), 2), "Interest": round(sum(r.amount for r in interest), 2)}
    assert s["income_records_added"] == len(salaries) + len(interest)
    assert s["transactions_added"] == len(BANK) - len(salaries) - len(interest)
    assert s["card_payments"] == sum(r.truth == "Card Payment" for r in BANK)
    assert s["transfers"] == sum(r.truth == "Transfer" for r in BANK)
    assert s["refunds"] == sum(r.truth.startswith("refund") for r in BANK)
    assert s["unrecognised_credits"] == sum(r.truth == "unrecognised" for r in BANK)
    assert s["investment_outflow"] == round(sum(r.amount for r in BANK if r.truth == "Investment"), 2)
    assert not {"Card Payment", "Transfer", "Investment"} & set(s["spend_by_category"])      # money moved is not spending
    assert s["money_moved"]["Card Payment"] == round(sum(r.amount for r in BANK if r.truth == "Card Payment"), 2)
    # every row lands in the right table with the right class
    with SessionLocal() as db:
        imp = ivy.bank["id"]
        txs = db.scalars(select(M.Transaction).where(M.Transaction.import_id == imp)).all()
        got_side = Counter(t.category for t in txs if t.type == "debit" and t.category in BANK_SIDE)
        merch = [t for t in txs if t.type == "debit" and t.category not in BANK_SIDE]
    # bank-side classes (rules) are exact
    assert got_side == Counter(r.truth for r in BANK if r.type == "debit" and r.truth in BANK_SIDE)
    # merchant rows: decided by the approved categoriser (confidence stored; < 0.5 sent for review) or left for the person.
    # Phase 6: the categoriser is trained on US card data, so its accuracy on these Indian narrations is NOT asserted
    # (it was 100% only for the synthetic-trained model on its own synthetic narrations).
    assert len(merch) == sum(r.type == "debit" and r.truth not in BANK_SIDE for r in BANK)
    for t in merch:
        assert t.category_source in ("model", "none", "user_rule")
        if t.category_source == "model":
            assert t.confidence is not None and bool(t.needs_review) == (True if categoriser.SUGGESTION_ONLY else t.confidence < 0.5)
        if t.category_source == "none":
            assert t.category is None and t.needs_review
    truth = {r.desc: r.truth for r in BANK}
    agree = sum(truth.get(t.raw_description) == t.category for t in merch) / len(merch)
    print(f"merchant-category agreement with the fixture's labels (information only, not a claim): {agree:.0%}")
    # account attribution and the verified closing balance
    assert all(t.account_id == ivy.acc and t.card_id is None for t in txs)
    assert s["balance"]["applied"] and s["balance"]["closing_balance"] == BANK[-1].balance


def test_card_import_is_attributed_to_the_card_and_never_counts_payments_as_spend(ivy):
    s = ivy.cardimp["summary"]
    assert ivy.cardimp["status"] == "done" and s["income_records_added"] == 0
    with SessionLocal() as db:
        txs = db.scalars(select(M.Transaction).where(M.Transaction.import_id == ivy.cardimp["id"])).all()
        card = db.get(M.CreditCard, ivy.card)
    assert all(t.card_id == ivy.card and t.account_id is None for t in txs)
    assert {t.category for t in txs if t.type == "credit" and "refund" not in (t.flags or "")} == {"Card Payment"}
    assert s["refunds"] == sum(r.truth.startswith("refund") for r in CARD)
    assert card.outstanding == 12000                                   # never invented from a statement without balances
    assert "Card statements do not carry a running balance" in s["balance"]["reason"]


def test_import_flows_into_identity_cash_flow_and_models(ivy):
    a, b = ivy.after, ivy.before
    cf = a["cash_flow"]
    months = 24
    income = sum(r.amount for r in BANK if r.truth.startswith("income"))
    # spend = bank debits that are expenses + card spends - refunds (card bills, transfers, investments excluded)
    spend = sum(r.amount for r in BANK + CARD if r.type == "debit" and r.truth not in ("Card Payment", "Transfer", "Investment")) \
        - sum(r.amount for r in BANK + CARD if r.truth.startswith("refund"))
    assert cf["income_known"] and cf["spending_known"]
    assert cf["avg_monthly_income"] == pytest.approx(income / months, abs=0.05)
    assert cf["avg_monthly_expenses"] == pytest.approx(spend / months, abs=0.05)
    # net worth moved by exactly the balance change of the imported account
    assert a["net_worth"]["net_worth"] - b["net_worth"]["net_worth"] == pytest.approx(BANK[-1].balance - 50000, abs=0.5)
    assert a["health_score"]["score"] is not None and b["health_score"]["score"] is None
    assert a["fire"]["available"] and a["tax"]["available"] and a["ml_errors"] == {}
    from app.ml import provenance as PV
    from app.ml.anomaly import NOT_SCORED
    if "forecast" in PV.active():
        assert a["ml"]["forecast"]["available"]
    else:                                        # the trained forecaster failed its baseline: reported as off, not an error
        assert a["ml"]["forecast"]["model_status"] == "awaiting_approved_model"
    if "anomaly" in PV.active():
        with SessionLocal() as db:
            uid = db.scalar(select(M.User.id).where(M.User.internal_id == ivy.pid))
            cats = db.scalars(select(M.Transaction.category).where(M.Transaction.user_id == uid, M.Transaction.type == "debit")).all()
        assert a["ml"]["anomaly"]["transactions_scored"] == sum(c not in NOT_SCORED for c in cats)   # every imported spend scored
    else:
        assert a["ml"]["anomaly"]["available"] is False
    assert len(a["recommendations"]) > 0
    pdf = ivy.get(f"/api/profiles/{ivy.pid}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_insights_show_where_money_goes_recurring_income_and_investments(ivy):
    i = ivy.get(f"/api/profiles/{ivy.pid}/insights").json()
    assert i["available"] and i["coverage"]["months"] == 24
    cats = {c["category"]: c["total"] for c in i["where"]["categories"]}
    assert cats["Rent"] == 25000 * 24 and cats["EMI"] == 15000 * 24
    rec = {r["merchant"]: r for r in i["recurring"]["items"]}
    assert rec["Netflix"]["cadence"] == "monthly" and rec["Netflix"]["typical_amount"] == 649 and rec["Netflix"]["status"] == "active"
    assert any(r["category"] == "Rent" and r["cadence"] == "monthly" for r in rec.values())
    assert any(r["category"] == "Investment" and r["kind"] == "investment" for r in rec.values())
    assert any(r["category"] == "EMI" and r["kind"] == "loan" for r in rec.values())
    assert i["investments"]["total_invested"] == 10000 * 24
    sal = i["income"]["salary"]
    assert sal["months_received"] == 24 and sal["regularity_pct"] == 100 and sal["typical_day"] == 1
    assert sal["changes"] and sal["changes"][-1]["from"] == 95000 and sal["changes"][-1]["to"] == 105000
    assert len(i["merchants"]) > 5 and i["changes"]["available"] and "year_over_year" in i["changes"]
    assert len(i["trend"]["months"]) == 24
    # filters keep attribution: the card view has only card rows and no income
    ci = ivy.get(f"/api/profiles/{ivy.pid}/insights", params={"card_id": ivy.card}).json()
    assert ci["income"] is None and ci["coverage"]["transactions"] == len(CARD)
    assert ivy.get(f"/api/profiles/{ivy.pid}/insights", params={"card_id": 999999}).status_code == 404


def test_insights_work_on_demo_sandboxes_too():
    c = signed_in_client("demo")
    sb = c.post("/api/demo/explore", json={"template_id": "FINORA_USER_001"})
    assert sb.status_code == 200, sb.text
    pid = sb.json()["profile"]["internal_id"]
    i = c.get(f"/api/profiles/{pid}/insights").json()
    assert i["available"] and i["where"]["total_spend"] > 0 and i["income"]["total"] > 0


# ---------------------------------------------------------------- duplicates & overlaps
def test_same_file_and_overlapping_statements_never_double_count(ivy):
    again = ivy.post(f"/api/profiles/{ivy.pid}/imports", files={"file": ("hdfc.csv", io.BytesIO(F.hdfc(BANK)), "text/csv")}).json()
    assert again["same_file_imported"]
    r = ivy.post(f"/api/profiles/{ivy.pid}/imports/{again['id']}/start", json={"account_id": ivy.acc})
    assert r.status_code == 409                                            # warned first
    ivy.post(f"/api/profiles/{ivy.pid}/imports/{again['id']}/start", json={"account_id": ivy.acc, "allow_same_file": True})
    s = ivy.get(f"/api/profiles/{ivy.pid}/imports/{again['id']}").json()["summary"]
    assert s["transactions_added"] == 0 and s["income_records_added"] == 0 and s["duplicates_skipped"] == len(BANK)
    # a different layout of an overlapping period (last 6 months, ICICI-style) adds nothing either
    tail = [r for r in BANK if r.date >= __import__("datetime").date(2026, 5, 1)]
    assert 100 < len(tail) < len(BANK)
    _, s2 = _import(ivy, ivy.pid, F.icici(tail), "icici.csv", account_id=ivy.acc)
    assert s2["summary"]["duplicates_skipped"] == len(tail) and s2["summary"]["transactions_added"] == 0


def test_genuine_identical_rows_on_the_same_day_are_kept():
    c = signed_in_client("twins")
    pid, acc, *_ = _profile(c)
    csv = ("Date,Narration,Withdrawal,Deposit,Balance\n"
           "01/10/2026,UPI/DR/1/DMRC/YESB/dmrc@ybl/Payment,40.00,,1000.00\n"
           "01/10/2026,UPI/DR/1/DMRC/YESB/dmrc@ybl/Payment,40.00,,960.00\n"
           "01/10/2026,UPI/DR/1/DMRC/YESB/dmrc@ybl/Payment,40.00,,920.00\n").encode()
    _, s = _import(c, pid, csv, account_id=acc)
    assert s["summary"]["transactions_added"] == 3
    # a statement for the next days that repeats only one of them adds only the new rows
    more = ("Date,Narration,Withdrawal,Deposit,Balance\n01/10/2026,UPI/DR/1/DMRC/YESB/dmrc@ybl/Payment,40.00,,920.00\n"
            "02/10/2026,UPI/DR/1/DMRC/YESB/dmrc@ybl/Payment,40.00,,880.00\n").encode()
    _, s2 = _import(c, pid, more, account_id=acc)
    assert s2["summary"]["transactions_added"] == 1 and s2["summary"]["duplicates_skipped"] == 1


def test_possible_duplicate_of_a_hand_entered_row_is_flagged_not_dropped():
    c = signed_in_client("manual")
    pid, acc, *_ = _profile(c)
    c.post(f"/api/profiles/{pid}/records/transactions", json={"date": "2026-10-05", "amount": 2500, "description": "dinner with team",
                                                              "account_id": acc})
    csv = "Date,Narration,Withdrawal,Deposit\n05/10/2026,POS 4521XXXXXXXX1111 BARBEQUENATION PUNE,2500,\n".encode()
    _, s = _import(c, pid, csv, account_id=acc)
    assert s["summary"]["transactions_added"] == 1 and s["summary"]["possible_duplicates"] == 1
    q = c.get(f"/api/profiles/{pid}/review").json()
    assert any("entered by hand" in (it["reason"] or "") for g in q["groups"] for it in g["items"])


# ---------------------------------------------------------------- malformed & partial
@pytest.mark.parametrize("content,needle", [
    (b"", "empty"),
    (b"\x00\x01\x02\xff\xfe garbage", "header row"),
    (b"foo,bar\n1,2\n", "header row"),
    (b"Name,Address\nA,B\n", "header row"),
])
def test_malformed_files_are_rejected_with_a_reason(ivy, content, needle):
    r = ivy.post(f"/api/profiles/{ivy.pid}/imports", files={"file": ("x.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 422 and needle in r.json()["detail"].lower()


def test_bad_rows_are_counted_not_guessed():
    c = signed_in_client("badrows")
    pid, acc, *_ = _profile(c)
    csv = ("Date,Narration,Withdrawal,Deposit\n"
           "05/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,450,\n"
           "31/02/2026,IMPOSSIBLE DATE,100,\n"
           "06/10/2026,NO AMOUNT,,\n"
           "07/10/2026,TEXT AMOUNT,abc,\n"
           "Opening Balance,,,\n"
           "08/10/2026,UPI/DR/1/ZOMATO/HDFC/zomato@ybl,300,,EXTRA,COLUMNS\n"
           "09/10/2026,UPI/DR/1/UBER/AXIS/uber@okaxis/Payment,250,\n").encode()
    _, s = _import(c, pid, csv, account_id=acc)
    sm = s["summary"]
    assert sm["transactions_added"] == 2 and sm["rows_dropped"] == 5
    assert sm["dropped"]["wrong number of columns"] == 1 and sm["dropped"]["no valid amount"] == 2


def test_row_and_size_limits(ivy, monkeypatch):
    monkeypatch.setattr(SI, "STATEMENT_MAX_ROWS", 10)
    monkeypatch.setattr(P, "MAX_ROWS", 10)
    r = ivy.post(f"/api/profiles/{ivy.pid}/imports", files={"file": ("x.csv", io.BytesIO(F.hdfc(BANK[:30], junk=False)), "text/csv")})
    assert r.status_code == 422 and "limit is 10" in r.json()["detail"]
    import app.routes.statements as R
    monkeypatch.setattr(R, "UPLOAD_MAX_BYTES", 2000)
    r = ivy.post(f"/api/profiles/{ivy.pid}/imports", files={"file": ("x.csv", io.BytesIO(F.hdfc(BANK)), "text/csv")})
    assert r.status_code == 413


def test_statement_without_balance_never_sets_a_balance():
    c = signed_in_client("nobal")
    pid, acc, *_ = _profile(c)
    _, s = _import(c, pid, F.generic_signed(BANK[:60], with_balance=False), account_id=acc)
    b = s["summary"]["balance"]
    assert not b["applied"] and not b["present"] and "no running balance" in b["reason"]
    with SessionLocal() as db:
        a = db.get(M.BankAccount, acc)
        assert a.balance == 50000 and a.balance_source is None


def test_unreconciled_balances_are_not_trusted():
    rows = [F.Row(r.date, r.desc, r.amount, r.type, r.truth, r.balance) for r in BANK[:80]]
    for r in rows[::3]:
        r.balance += 1000                                            # a corrupted running balance column
    p = P.parse(P.read_table(F.hdfc(rows)), kind="bank")
    assert not p.detection["balance"]["verified"] and "reconcile" in p.detection["balance"]["reason"]


def test_new_account_from_statement_needs_a_real_balance():
    c = signed_in_client("newacc")
    pid = c.post("/api/profiles", json={"name": "No Accounts", "age": 28}).json()["profile"]["internal_id"]
    _, s = _import(c, pid, F.generic_signed(BANK[:50], with_balance=False), new_account={"bank_name": "Axis Bank", "last4": "5555"})
    assert s["status"] == "failed" and "cannot know the account's balance" in s["error"]
    with SessionLocal() as db:                                         # rolled back: no account, no rows
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        assert not db.scalar(select(func.count()).select_from(M.BankAccount).where(M.BankAccount.user_id == uid))
        assert not db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.user_id == uid))
    _, s2 = _import(c, pid, F.hdfc(BANK[:50]), new_account={"bank_name": "Axis Bank", "last4": "5555"})
    assert s2["status"] == "done" and s2["summary"]["balance"]["applied"]
    acc = c.get(f"/api/profiles/{pid}/records/bank_accounts").json()["items"][0]
    assert acc["balance"] == BANK[49].balance and acc["balance_source"] == "statement" and acc["balance_as_of"] == BANK[49].date.isoformat()


def test_editing_a_statement_balance_by_hand_marks_it_manual(ivy):
    with SessionLocal() as db:
        assert db.get(M.BankAccount, ivy.acc).balance_source == "statement"
    c = signed_in_client("manualbal")
    pid, acc, *_ = _profile(c)
    _import(c, pid, F.hdfc(BANK[:20]), account_id=acc, update_balance=True)
    c.patch(f"/api/profiles/{pid}/records/bank_accounts/{acc}", json={"balance": 1000})
    with SessionLocal() as db:
        a = db.get(M.BankAccount, acc)
        assert a.balance == 1000 and a.balance_source == "manual" and a.balance_as_of is None


def test_attribution_rules(ivy):
    pv = ivy.post(f"/api/profiles/{ivy.pid}/imports", files={"file": ("c.csv", io.BytesIO(F.card_statement(CARD[:10])), "text/csv")}).json()
    for body, code in [({}, 422), ({"statement_kind": "card", "account_id": ivy.acc}, 422), ({"statement_kind": "bank", "card_id": ivy.card}, 422),
                       ({"account_id": 999999}, 422), ({"statement_kind": "card", "card_id": ivy.card, "mapping": {"date": "Nope"}}, 422)]:
        assert ivy.post(f"/api/profiles/{ivy.pid}/imports/{pv['id']}/start", json=body).status_code == code, body
    assert ivy.post(f"/api/profiles/{ivy.pid}/imports/{pv['id']}/cancel").json()["status"] == "cancelled"
    assert not SI.pending_path(pv["id"]).exists()


def test_column_mapping_can_be_corrected():
    c = signed_in_client("mapping")
    pid, acc, *_ = _profile(c)
    # headers Finora cannot recognise: the preview asks the person to map them instead of failing
    csv = "When,What,Out,In\n05/10/2026,UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment,450,\n06/10/2026,REFUND SWIGGY,,100\n".encode()
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("m.csv", io.BytesIO(csv), "text/csv")}).json()
    assert pv["detection"]["needs_mapping"] and pv["detection"]["headers"] == ["When", "What", "Out", "In"]
    r = c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": acc})
    assert r.status_code == 422 and "Map a column" in r.json()["detail"]
    r = c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": acc, "mapping": {"date": "When", "description": "What"}})
    assert r.status_code == 422 and "amount" in r.json()["detail"]
    c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start",
           json={"account_id": acc, "mapping": {"date": "When", "description": "What", "debit": "Out", "credit": "In"}})
    s = c.get(f"/api/profiles/{pid}/imports/{pv['id']}").json()["summary"]
    assert s["transactions_added"] == 2 and s["refunds"] == 1
    # a recognised layout can still be overridden (here: debit and credit columns swapped by the person)
    csv3 = "Date,Narration,Withdrawal,Deposit\n07/10/2026,UPI/DR/1/UBER/AXIS/uber@okaxis/Payment,,120\n".encode()
    pv3 = c.post(f"/api/profiles/{pid}/imports", files={"file": ("m3.csv", io.BytesIO(csv3), "text/csv")}).json()
    assert pv3["detection"]["mapping"] == {"date": "Date", "description": "Narration", "debit": "Withdrawal", "credit": "Deposit"}
    c.post(f"/api/profiles/{pid}/imports/{pv3['id']}/start",
           json={"account_id": acc, "mapping": {"date": "Date", "description": "Narration", "debit": "Deposit", "credit": "Withdrawal"}})
    s3 = c.get(f"/api/profiles/{pid}/imports/{pv3['id']}").json()["summary"]
    assert s3["by_category"] == {"Travel": 1}                          # read as a debit after the correction
    assert c.post(f"/api/profiles/{pid}/imports", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}).status_code == 422


# ---------------------------------------------------------------- review & corrections
def test_review_queue_and_corrections_change_the_numbers(ivy):
    q = ivy.get(f"/api/profiles/{ivy.pid}/review").json()
    p2p = next(g for g in q["groups"] if g["merchant"].upper() == "RAHUL SHARMA")
    assert p2p["count"] == sum(r.truth == "unrecognised" for r in BANK) and "not counted as income" in p2p["reason"]
    income_before = ivy.get(f"/api/profiles/{ivy.pid}/analysis").json()["cash_flow"]["avg_monthly_income"]
    r = ivy.post(f"/api/profiles/{ivy.pid}/review/classify",
                 json={"items": p2p["refs"], "income_type": "Other income", "remember": True})
    assert r.json()["moved_between_income_and_spending"] == p2p["count"] and r.json()["rules_saved"] == 1
    income_after = ivy.get(f"/api/profiles/{ivy.pid}/analysis").json()["cash_flow"]["avg_monthly_income"]
    assert income_after - income_before == pytest.approx(p2p["total"] / 24, abs=0.05)
    # the remembered rule classifies the same sender on the next import, with no review needed
    csv = "Date,Narration,Withdrawal,Deposit\n29/10/2026,UPI/CR/555/RAHUL SHARMA/okaxis/rent share,,4000\n".encode()
    _, s = _import(ivy, ivy.pid, csv, account_id=ivy.acc)
    assert s["summary"]["income_by_source"] == {"Other income": 4000.0} and s["summary"]["needs_review"] == 0
    assert s["summary"]["decided_by"] == {"user_rule": 1}
    # and back again: income -> transfer
    inc = [i for g in ivy.get(f"/api/profiles/{ivy.pid}/review").json()["groups"] for i in g["items"]]
    with SessionLocal() as db:
        rid = db.scalar(select(M.IncomeRecord.id).where(M.IncomeRecord.raw_description.like("%rent share%")))
    r2 = ivy.post(f"/api/profiles/{ivy.pid}/review/classify", json={"items": [{"kind": "income", "id": rid}], "category": "Transfer"})
    assert r2.json()["moved_between_income_and_spending"] == 1
    rules = ivy.get(f"/api/profiles/{ivy.pid}/category-rules").json()
    assert ivy.delete(f"/api/profiles/{ivy.pid}/category-rules/{rules[0]['id']}").status_code == 200


def test_correcting_a_spending_category_moves_the_spend(ivy):
    t = ivy.get(f"/api/profiles/{ivy.pid}/transactions", params={"category": "Dining", "limit": 1}).json()["items"][0]
    before = {c["category"]: c["total"] for c in ivy.get(f"/api/profiles/{ivy.pid}/insights").json()["where"]["categories"]}
    ivy.post(f"/api/profiles/{ivy.pid}/review/classify", json={"items": [{"kind": "tx", "id": t["id"]}], "category": "Health"})
    after = {c["category"]: c["total"] for c in ivy.get(f"/api/profiles/{ivy.pid}/insights").json()["where"]["categories"]}
    assert after["Dining"] == pytest.approx(before["Dining"] - t["amount"], abs=0.01)
    assert after["Health"] == pytest.approx(before["Health"] + t["amount"], abs=0.01)
    bad = ivy.post(f"/api/profiles/{ivy.pid}/review/classify", json={"items": [{"kind": "tx", "id": t["id"]}], "income_type": "Salary"})
    assert bad.status_code == 422                                     # a debit cannot become income


# ---------------------------------------------------------------- undo, cancel, failures, recovery
def test_undo_restores_the_profile_exactly():
    c = signed_in_client("undo")
    pid, acc, *_ = _profile(c)
    before = c.get(f"/api/profiles/{pid}/analysis").json()
    _, s = _import(c, pid, F.hdfc(BANK), account_id=acc, update_balance=True)
    mid = c.get(f"/api/profiles/{pid}/analysis").json()
    assert mid["net_worth"]["net_worth"] != before["net_worth"]["net_worth"]
    u = c.delete(f"/api/profiles/{pid}/imports/{s['id']}").json()
    assert u["status"] == "undone" and u["undo"]["balance_restored"]
    assert u["undo"]["transactions_removed"] + u["undo"]["income_records_removed"] == len(BANK)
    after = c.get(f"/api/profiles/{pid}/analysis").json()
    assert after["net_worth"] == before["net_worth"] and after["cash_flow"] == before["cash_flow"]
    assert c.delete(f"/api/profiles/{pid}/imports/{s['id']}").status_code == 409


def test_cancel_and_failure_leave_nothing_behind(monkeypatch):
    c = signed_in_client("cancel")
    pid, acc, *_ = _profile(c)
    pv = c.post(f"/api/profiles/{pid}/imports", files={"file": ("s.csv", io.BytesIO(F.hdfc(BANK)), "text/csv")}).json()
    real_run = SI.run
    monkeypatch.setattr("app.routes.statements.SI.run", lambda i: (SI.CANCEL.add(i), real_run(i)))
    c.post(f"/api/profiles/{pid}/imports/{pv['id']}/start", json={"account_id": acc})
    s = c.get(f"/api/profiles/{pid}/imports/{pv['id']}").json()
    assert s["status"] == "cancelled"
    monkeypatch.setattr("app.routes.statements.SI.run", real_run)

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(SI, "_summary", boom)                         # fails AFTER rows were saved in chunks
    _, s2 = _import(c, pid, F.hdfc(BANK), account_id=acc)
    assert s2["status"] == "failed" and "Nothing was saved" in s2["error"]
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        assert not db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.user_id == uid))
        assert not db.scalar(select(func.count()).select_from(M.IncomeRecord).where(M.IncomeRecord.user_id == uid))
        assert db.get(M.BankAccount, acc).balance == 50000


def test_interrupted_import_is_rolled_back_on_restart():
    c = signed_in_client("restart")
    pid, acc, *_ = _profile(c)
    with SessionLocal() as db:
        uid = db.scalar(select(M.User.id).where(M.User.internal_id == pid))
        from datetime import datetime, timedelta
        imp = M.StatementImport(user_id=uid, filename="x.csv", sha256="0" * 64, size_bytes=1, status="running",
                                heartbeat_at=datetime.utcnow() - timedelta(seconds=SI.STALE_AFTER + 60))
        db.add(imp)
        db.flush()
        db.add(M.Transaction(user_id=uid, ref="x", date=BANK[0].date, amount=1, raw_description="half saved", import_id=imp.id))
        db.commit()
        assert SI.recover_interrupted(db) >= 1
        assert db.get(M.StatementImport, imp.id).status == "failed"
        assert not db.scalar(select(func.count()).select_from(M.Transaction).where(M.Transaction.import_id == imp.id))


# ---------------------------------------------------------------- ownership
def test_ownership_and_templates(ivy):
    eve = signed_in_client("eve")
    imp = ivy.bank["id"]
    for method, url, kw in [("get", f"/api/profiles/{ivy.pid}/imports", {}), ("get", f"/api/profiles/{ivy.pid}/imports/{imp}", {}),
                            ("delete", f"/api/profiles/{ivy.pid}/imports/{imp}", {}), ("get", f"/api/profiles/{ivy.pid}/insights", {}),
                            ("get", f"/api/profiles/{ivy.pid}/review", {}),
                            ("post", f"/api/profiles/{ivy.pid}/review/confirm", {"json": {"items": [{"kind": "tx", "id": 1}]}}),
                            ("post", f"/api/profiles/{ivy.pid}/imports", {"files": {"file": ("s.csv", io.BytesIO(F.hdfc(BANK[:5])), "text/csv")}})]:
        assert getattr(eve, method)(url, **kw).status_code == 404, url
    # eve's own profile cannot reach ivy's import or rows by id
    epid, *_ = _profile(eve, "Eve")
    assert eve.get(f"/api/profiles/{epid}/imports/{imp}").status_code == 404
    with SessionLocal() as db:
        tid = db.scalar(select(M.Transaction.id).where(M.Transaction.import_id == imp))
    assert eve.post(f"/api/profiles/{epid}/review/confirm", json={"items": [{"kind": "tx", "id": tid}]}).status_code == 404
    # demo templates are read-only; their insights are readable
    t = eve.post(f"/api/profiles/FINORA_USER_001/imports", files={"file": ("s.csv", io.BytesIO(F.hdfc(BANK[:5])), "text/csv")})
    assert t.status_code == 403
    assert eve.get("/api/profiles/FINORA_USER_001/insights").status_code == 200


def test_sandbox_has_the_same_import_features():
    c = signed_in_client("sbimport")
    r = c.post("/api/demo/explore", json={"template_id": "FINORA_USER_002"})
    pid = r.json()["profile"]["internal_id"]
    acc = c.get(f"/api/profiles/{pid}/records/bank_accounts").json()["items"][0]["id"]
    _, s = _import(c, pid, F.hdfc(BANK[-60:]), account_id=acc)
    assert s["status"] == "done" and s["summary"]["transactions_added"] > 0
    assert c.post(f"/api/profiles/{pid}/reset").status_code == 200
    with SessionLocal() as db:
        assert not db.scalar(select(func.count()).select_from(M.StatementImport).join(M.User, M.User.id == M.StatementImport.user_id)
                             .where(M.User.internal_id == pid))


# ---------------------------------------------------------------- scale
def test_150k_row_file_imports_with_progress_and_a_verified_balance(monkeypatch):
    c = signed_in_client("big")
    pid, acc, *_ = _profile(c)
    content, closing = F.big_bank(150_000)
    assert len(content) < 25_000_000
    seen = []
    real = SI._progress
    monkeypatch.setattr(SI, "_progress", lambda i, st, d=0, n=0: (seen.append((st, d, n)), real(i, st, d, n)))
    t0 = time.time()
    pv, s = _import(c, pid, content, "big.csv", account_id=acc)
    took = time.time() - t0
    assert pv["rows_total"] == 150_000 and s["status"] == "done"
    sm = s["summary"]
    assert sm["transactions_added"] + sm["income_records_added"] == 150_000 and sm["balance"]["verified"]
    assert sm["balance"]["closing_balance"] == closing
    stages = [x[0] for x in seen]
    for st in ["reading", "parsing", "categorising", "saving", "analysis", "done"]:
        assert st in stages
    assert sum(1 for x in seen if x[0] == "saving") >= 70                  # saved in many short chunks
    assert sum(1 for x in seen if x[0] == "categorising") >= 3
    assert took < 120, took
    assert c.get(f"/api/profiles/{pid}/insights").status_code == 200
    c.delete(f"/api/profiles/{pid}")

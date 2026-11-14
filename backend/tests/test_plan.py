"""Phase 5: Finora Plan - picture, diagnosis, ranked actions, plan assumptions and the scenario engine.

Impacts are re-derived here independently from the underlying engines (debt payoff simulation, FIRE projection,
pool arithmetic) - proving they are baseline-minus-scenario calculations, not hard-coded numbers - and every write is
shown to leave the historical records untouched.
"""
import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select

from app import models as M
from app.database import SessionLocal
from app.services import calculations as C
from app.services import fire as F
from app.services import plan as PL

from .conftest import signed_in_client

DEMOS = ["FINORA_USER_001", "FINORA_USER_002", "FINORA_USER_003", "FINORA_USER_004"]
SOURCE_TABLES = [M.Transaction, M.IncomeRecord, M.BankAccount, M.CreditCard, M.Loan, M.SIP, M.Goal, M.StockHolding,
                 M.MutualFundHolding, M.FixedDeposit, M.OtherAsset, M.InsurancePolicy, M.Property, M.RecurringPayment]


def fingerprint(uid: int) -> str:
    """Hash of every historical/source record of a profile (and card statements)."""
    h = hashlib.sha256()
    with SessionLocal() as db:
        for model in SOURCE_TABLES:
            rows = db.scalars(select(model).where(model.user_id == uid).order_by(model.id)).all()
            for r in rows:
                h.update(json.dumps({c.key: str(getattr(r, c.key)) for c in model.__table__.columns}, sort_keys=True).encode())
        card_ids = [c for (c,) in db.execute(select(M.CreditCard.id).where(M.CreditCard.user_id == uid))]
        for s in db.scalars(select(M.CardStatement).where(M.CardStatement.card_id.in_(card_ids)).order_by(M.CardStatement.id)):
            h.update(json.dumps({c.key: str(getattr(s, c.key)) for c in M.CardStatement.__table__.columns}, sort_keys=True).encode())
    return h.hexdigest()


@pytest.fixture(scope="module")
def zoe():
    c = signed_in_client("zoe")
    c.sb = {}
    for t in DEMOS:
        c.sb[t] = c.post("/api/demo/explore", json={"template_id": t}).json()["profile"]["internal_id"]
    return c


def _uid(pid):
    with SessionLocal() as db:
        return db.scalar(select(M.User.id).where(M.User.internal_id == pid))


def _base(pid):
    from app.routes import common
    with SessionLocal() as db:
        u = db.scalar(select(M.User).where(M.User.internal_id == pid))
        a = common.get_analysis(db, u)
        goals = [{"id": g.id, "name": g.name, "target_amount": g.target_amount, "target_date": g.target_date}
                 for g in db.scalars(select(M.Goal).where(M.Goal.user_id == u.id))]
    return PL.base_from(a, goals), a


# ---------------------------------------------------------------- structure
@pytest.mark.parametrize("tid", DEMOS)
def test_plan_has_picture_3_to_6_findings_and_3_to_5_ranked_actions(zoe, tid):
    p = zoe.get(f"/api/profiles/{zoe.sb[tid]}/plan").json()
    pic = p["picture"]
    for k in ("income", "expenses", "surplus", "balances", "debt", "emi", "net_worth", "runway_months", "health_score",
              "investments", "fire_progress_pct", "completeness_pct"):
        assert k in pic
    assert 3 <= len(p["diagnosis"]) <= 6
    for d in p["diagnosis"]:
        assert d["finding"] and d["evidence"] and d["why"] and d["source"] and d["confidence"] and d["detail_link"].startswith("/")
    assert 3 <= len(p["actions"]) <= 5, [a["code"] for a in p["actions"]]
    assert [a["rank"] for a in p["actions"]] == list(range(1, len(p["actions"]) + 1))
    assert [a["benefit"] for a in p["actions"]] == sorted((a["benefit"] for a in p["actions"]), reverse=True)
    for a in p["actions"]:
        assert a["step"] and a["evidence"] and a["impact"]["label"] and set(a["effect"]) >= {
            "surplus", "debt_free_months", "runway_months", "health_score", "fire_age"}


# ---------------------------------------------------------------- impact = baseline - scenario, re-derived independently
@pytest.mark.parametrize("tid", DEMOS)
def test_every_action_effect_is_baseline_minus_scenario(zoe, tid):
    pid = zoe.sb[tid]
    p = zoe.get(f"/api/profiles/{pid}/plan").json()
    b, a = _base(pid)
    base = PL.evaluate(b, [])
    assert p["baseline"]["surplus"] == pytest.approx(a["cash_flow"]["avg_monthly_income"] - a["cash_flow"]["avg_monthly_expenses"], abs=0.01)
    assert p["baseline"]["health_score"] == a["health_score"]["score"] or p["baseline"]["runway_months"] != a["liquidity"]["runway_months"]
    for act in p["actions"]:
        amt = act["params"].get("amount")
        e = act["effect"]
        if act["kind"] == "extra_debt_repayment":
            plain = C.simulate_payoff(b.debts, 0, "avalanche")
            extra = C.simulate_payoff(b.debts, amt, "avalanche")
            assert e["debt_free_months"] == extra["months_to_debt_free"] - plain["months_to_debt_free"]
            assert -e["debt_interest"] == pytest.approx(plain["total_interest"] - extra["total_interest"])
            assert act["impact"]["inr"] == pytest.approx(plain["total_interest"] - extra["total_interest"])
            assert e["surplus"] == -amt
        elif act["kind"] == "spending_cap":
            assert e["surplus"] == pytest.approx(amt)
            assert act["scenario"]["runway_months"] == pytest.approx(round(base["pool_in_12m"] / (b.expenses - amt), 2), abs=0.01)
            assert act["impact"]["inr"] == pytest.approx(amt * 12)
        elif act["kind"] == "sip":
            assert e["surplus"] == -amt
            fp = F.project(b.corpus, b.monthly_invest + amt, b.age, max(1.0, (b.expenses - b.emi) * 12), retirement_age_target=b.retirement_target)
            assert act["scenario"]["fire_age"] == fp["fire_age"]
        elif act["kind"] == "emergency_fund_contribution":
            assert e["pool_in_12m"] == pytest.approx(12 * amt) and e["surplus"] == -amt
        # whatever the kind: the effect equals the engine's own scenario - baseline
        scen = PL.evaluate(b, [{"kind": act["kind"], "params": act["params"]}])
        assert e == PL.compare(base, scen)


def test_delayed_purchase_moves_a_goal_out_of_the_12_month_window():
    c = signed_in_client("delay")
    pid = c.post("/api/profiles", json={"name": "Goal Person", "age": 30}).json()["profile"]["internal_id"]
    c.post(f"/api/profiles/{pid}/records/bank_accounts", json={"bank_name": "HDFC", "last4": "1111", "balance": 200000})
    for m in range(5, 11):
        c.post(f"/api/profiles/{pid}/records/income", json={"source": "Salary", "amount": 80000, "date": f"2026-{m:02d}-01"})
        c.post(f"/api/profiles/{pid}/records/transactions", json={"date": f"2026-{m:02d}-10", "amount": 50000, "description": "IMPS/P2A/1/RENT FLAT"})
    g = c.post(f"/api/profiles/{pid}/records/goals", json={"name": "Car", "target_amount": 150000, "target_date": "2027-04-30",
                                                         "current_amount": 0}).json()
    p = c.get(f"/api/profiles/{pid}/plan").json()
    act = next(a for a in p["actions"] if a["kind"] == "delayed_purchase")
    assert act["params"]["goal_id"] == g["id"] and act["baseline"]["pool_in_12m"] == 200000 - 150000
    assert act["effect"]["pool_in_12m"] == 150000                     # the payment leaves the 12-month window
    assert act["effect"]["runway_months"] == pytest.approx(round(200000 / 50000, 2) - round(50000 / 50000, 2), abs=0.01)


# ---------------------------------------------------------------- accept / edit / dismiss / detail, history untouched
def test_accept_edit_dismiss_detail_never_change_history(zoe):
    pid = zoe.sb["FINORA_USER_003"]
    uid = _uid(pid)
    before = fingerprint(uid)
    a_before = zoe.get(f"/api/profiles/{pid}/analysis").json()
    p = zoe.get(f"/api/profiles/{pid}/plan").json()
    acts = {a["kind"]: a for a in p["actions"]}
    debt, sip = acts["extra_debt_repayment"], acts["sip"]
    # detail
    d = zoe.get(f"/api/profiles/{pid}/plan/actions/{debt['code']}").json()
    assert d["status"] == "open" and d["effect"] == debt["effect"] and d["history_untouched"]
    # accept two actions -> the plan scenario is exactly the engine run with both assumptions
    r = zoe.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": debt["kind"], "params": debt["params"], "source_code": debt["code"],
                                                                "title": debt["title"]})
    assert r.status_code == 201
    zoe.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": sip["kind"], "params": sip["params"], "source_code": sip["code"],
                                                            "title": sip["title"]})
    plan = zoe.get(f"/api/profiles/{pid}/plan").json()
    b, _ = _base(pid)
    both = PL.evaluate(b, [{"kind": debt["kind"], "params": debt["params"]}, {"kind": sip["kind"], "params": sip["params"]}])
    assert plan["with_plan"]["surplus"] == both["surplus"] and plan["with_plan"]["fire_age"] == both["fire_age"]
    assert plan["with_plan"]["debt_free_months"] == both["debt_free_months"]
    assert plan["plan_effect"]["surplus"] == -(debt["params"]["amount"] + sip["params"]["amount"])
    assert {x["status"] for x in plan["actions"] if x["code"] in (debt["code"], sip["code"])} == {"accepted"}
    # edit: double the extra repayment -> debt-free date moves again, recomputed
    aid = next(x["id"] for x in plan["assumptions"] if x["source_code"] == debt["code"])
    edited = zoe.patch(f"/api/profiles/{pid}/plan/assumptions/{aid}", json={"params": {"amount": debt["params"]["amount"] * 2}}).json()["plan"]
    sim = C.simulate_payoff(b.debts, debt["params"]["amount"] * 2, "avalanche")
    assert edited["with_plan"]["debt_free_months"] == sim["months_to_debt_free"]
    from app.services.plan import _inr
    assert next(x for x in edited["assumptions"] if x["id"] == aid)["title"] == f"Pay {_inr(debt['params']['amount'] * 2)} extra a month on your debts"
    # dismiss and restore an open action
    open_act = next(a for a in plan["actions"] if a["status"] == "open")
    after_dismiss = zoe.post(f"/api/profiles/{pid}/plan/dismiss", json={"code": open_act["code"]}).json()["plan"]
    assert next(a for a in after_dismiss["actions"] if a["code"] == open_act["code"])["status"] == "dismissed"
    assert after_dismiss["with_plan"] == edited["with_plan"]                 # dismissing changes no outcome
    assert zoe.delete(f"/api/profiles/{pid}/plan/dismiss/{open_act['code']}").status_code == 200
    # preview never stores anything
    n = len(zoe.get(f"/api/profiles/{pid}/plan").json()["assumptions"])
    pv = zoe.post(f"/api/profiles/{pid}/plan/preview", json={"assumptions": [{"kind": "sip", "params": {"amount": 5000}}]}).json()
    assert pv["effect"]["surplus"] is not None and len(zoe.get(f"/api/profiles/{pid}/plan").json()["assumptions"]) == n
    # HISTORY: byte-for-byte the same records, and the history-based analysis is unchanged
    assert fingerprint(uid) == before
    a_after = zoe.get(f"/api/profiles/{pid}/analysis").json()
    for k in ("cash_flow", "net_worth", "liquidity", "debt", "health_score", "fire"):
        assert a_after[k] == a_before[k], k
    with SessionLocal() as db:
        assert not db.scalars(select(M.Transaction).where(M.Transaction.user_id == uid, M.Transaction.date > date(2026, 10, 31))).all()
    # remove everything -> back to baseline
    for x in zoe.get(f"/api/profiles/{pid}/plan").json()["assumptions"]:
        zoe.delete(f"/api/profiles/{pid}/plan/assumptions/{x['id']}")
    final = zoe.get(f"/api/profiles/{pid}/plan").json()
    assert final["with_plan"] == final["baseline"] and final["plan_effect"]["surplus"] == 0
    assert fingerprint(uid) == before


def test_assumptions_persist_across_cache_and_flag_over_commitment(zoe):
    from app.routes import common
    pid = zoe.sb["FINORA_USER_002"]
    surplus = zoe.get(f"/api/profiles/{pid}/plan").json()["baseline"]["surplus"]
    zoe.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": "sip", "params": {"amount": max(1000, surplus + 5000)}})
    common.invalidate()                                                     # like a server restart
    p = zoe.get(f"/api/profiles/{pid}/plan").json()
    assert len(p["assumptions"]) == 1 and p["over_committed"] is True and p["with_plan"]["surplus"] < 0


# ---------------------------------------------------------------- validation, ownership, partial data
def test_validation(zoe):
    pid = zoe.sb["FINORA_USER_001"]
    for body in [{"kind": "sip", "params": {"amount": 0}}, {"kind": "sip", "params": {"amount": 100, "x": 1}},
                 {"kind": "teleport", "params": {"amount": 100}}, {"kind": "delayed_purchase", "params": {"goal_id": 999999, "months_delay": 3}},
                 {"kind": "spending_cap", "params": {"amount": 10 ** 7}}]:
        assert zoe.post(f"/api/profiles/{pid}/plan/assumptions", json=body).status_code == 422, body
    c = signed_in_client("nodebt")
    p2 = c.post("/api/profiles", json={"name": "No Debt", "age": 30}).json()["profile"]["internal_id"]
    assert c.post(f"/api/profiles/{p2}/plan/assumptions", json={"kind": "extra_debt_repayment", "params": {"amount": 1000}}).status_code == 422


def test_ownership_and_templates(zoe):
    eve = signed_in_client("eveplan")
    pid = zoe.sb["FINORA_USER_001"]
    assert eve.get(f"/api/profiles/{pid}/plan").status_code == 404
    assert eve.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": "sip", "params": {"amount": 1000}}).status_code == 404
    assert eve.post(f"/api/profiles/{pid}/plan/preview", json={"assumptions": []}).status_code == 404
    t = eve.get("/api/profiles/FINORA_USER_001/plan")
    assert t.status_code == 200 and t.json()["read_only"] is True
    assert eve.post("/api/profiles/FINORA_USER_001/plan/assumptions", json={"kind": "sip", "params": {"amount": 1000}}).status_code == 403
    # another user's assumption id cannot be edited from your own profile
    mine = eve.post("/api/profiles", json={"name": "Eve Own", "age": 30}).json()["profile"]["internal_id"]
    aid = zoe.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": "sip", "params": {"amount": 1000}}).json()["id"]
    assert eve.patch(f"/api/profiles/{mine}/plan/assumptions/{aid}", json={"params": {"amount": 5}}).status_code == 404
    assert eve.delete(f"/api/profiles/{mine}/plan/assumptions/{aid}").status_code == 404


def test_empty_and_partial_profiles_get_an_honest_plan():
    c = signed_in_client("emptyplan")
    pid = c.post("/api/profiles", json={"name": "Empty Person", "age": 30}).json()["profile"]["internal_id"]
    p = c.get(f"/api/profiles/{pid}/plan").json()
    assert p["available"] is False and "income and spending" in p["reason"] and p["actions"] == []
    assert 3 <= len(p["diagnosis"]) and all(d["severity"] == "info" for d in p["diagnosis"])
    assert not any("₹0" in d["evidence"] or "No personal health" in d["finding"] for d in p["diagnosis"])   # missing is not zero
    assert p["baseline"]["surplus"] is None and p["with_plan"]["surplus"] is None


def test_reset_and_delete_remove_plan_assumptions(zoe):
    pid = zoe.sb["FINORA_USER_004"]
    zoe.post(f"/api/profiles/{pid}/plan/assumptions", json={"kind": "sip", "params": {"amount": 1000}})
    zoe.post(f"/api/profiles/{pid}/reset")
    assert zoe.get(f"/api/profiles/{pid}/plan").json()["assumptions"] == []

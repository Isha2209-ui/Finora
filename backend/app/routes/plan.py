"""Finora Plan.

    GET    /api/profiles/{id}/plan                          picture, diagnosis, ranked actions, assumptions, baseline vs plan
    GET    /api/profiles/{id}/plan/actions/{code}           one action in detail (full scenario breakdown and method)
    POST   /api/profiles/{id}/plan/preview                  what-if: evaluate assumptions WITHOUT saving (read access)
    POST   /api/profiles/{id}/plan/assumptions              accept an action (optionally edited) -> stored assumption
    PATCH  /api/profiles/{id}/plan/assumptions/{aid}        edit an accepted assumption
    DELETE /api/profiles/{id}/plan/assumptions/{aid}        remove it from the plan
    POST   /api/profiles/{id}/plan/dismiss                  dismiss an action;   DELETE .../plan/dismiss/{code} restores it

Accepting, editing or dismissing only writes plan_assumptions. Transactions, income, balances and every other record are
never touched (tests assert this).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import ProfileCtx, audit, profile_reader, profile_writer
from ..database import get_db
from ..services import plan as PL
from . import common

router = APIRouter(prefix="/api", tags=["plan"])


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AmountP(_P):
    amount: float = Field(gt=0, le=10_000_000)


class DebtP(AmountP):
    target: str | None = Field(None, max_length=120)


class CapP(AmountP):
    category: str | None = Field(None, max_length=40)


class DelayP(_P):
    goal_id: int
    months_delay: int = Field(ge=1, le=60)
    amount: float | None = Field(None, ge=0)


PARAMS = {"extra_debt_repayment": DebtP, "spending_cap": CapP, "emergency_fund_contribution": AmountP, "sip": AmountP,
          "delayed_purchase": DelayP}
Kind = Literal["extra_debt_repayment", "spending_cap", "emergency_fund_contribution", "sip", "delayed_purchase"]


class AssumptionIn(_P):
    kind: Kind
    params: dict
    source_code: str | None = Field(None, max_length=60)
    title: str | None = Field(None, max_length=160)


class AssumptionPatch(_P):
    params: dict


class PreviewIn(_P):
    assumptions: list[AssumptionIn] = Field(default_factory=list, max_length=20)
    include_accepted: bool = True


class DismissIn(_P):
    code: str = Field(min_length=3, max_length=60)


def _validate(db: Session, uid: int, analysis: dict, kind: str, params: dict) -> dict:
    try:
        clean = PARAMS[kind](**params).model_dump(exclude_none=True)
    except ValidationError as e:
        raise HTTPException(422, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
    if kind == "extra_debt_repayment" and not analysis["debt"].get("debts"):
        raise HTTPException(422, "There is no recorded loan or card balance to repay.")
    if kind == "spending_cap":
        exp = analysis["cash_flow"].get("avg_monthly_expenses")
        if exp is None:
            raise HTTPException(422, "A spending cap needs spending history.")
        if clean["amount"] > exp:
            raise HTTPException(422, "The cut cannot be larger than your average monthly spending.")
    if kind == "delayed_purchase":
        g = db.get(M.Goal, clean["goal_id"])
        if g is None or g.user_id != uid:
            raise HTTPException(422, "That goal does not belong to this profile.")
        clean["amount"] = float(g.target_amount)
    return clean


def _goal_name(db: Session, params: dict) -> str | None:
    g = db.get(M.Goal, params["goal_id"]) if params.get("goal_id") else None
    return g.name if g else None


def _accepted(db: Session, uid: int) -> tuple[list[dict], set[str]]:
    rows = db.scalars(select(M.PlanAssumption).where(M.PlanAssumption.user_id == uid).order_by(M.PlanAssumption.id)).all()
    acc = [{"id": r.id, "kind": r.kind, "kind_label": PL.KINDS.get(r.kind, r.kind), "params": r.params, "title": r.title,
            "source_code": r.source_code, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()}
           for r in rows if r.status == "accepted"]
    return acc, {r.source_code for r in rows if r.status == "dismissed" and r.source_code}


def _goals(db: Session, uid: int) -> list[dict]:
    return [{"id": g.id, "name": g.name, "target_amount": g.target_amount, "target_date": g.target_date}
            for g in db.scalars(select(M.Goal).where(M.Goal.user_id == uid))]


def _plan(db: Session, ctx: ProfileCtx) -> dict:
    a = common.get_analysis(db, ctx.profile)
    acc, dismissed = _accepted(db, ctx.profile.id)
    out = PL.build(a, _goals(db, ctx.profile.id), acc, dismissed)
    out["read_only"] = ctx.profile.kind == "template"
    out["profile"] = {"name": a["profile"]["name"], "age": a["profile"]["age"], "kind": ctx.profile.kind}
    return out


@router.get("/profiles/{internal_id}/plan", summary="Finora Plan: picture, diagnosis, ranked actions and the scenario")
def get_plan(ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    return _plan(db, ctx)


@router.get("/profiles/{internal_id}/plan/actions/{code}", summary="One plan action in detail")
def action_detail(code: str, ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    a = common.get_analysis(db, ctx.profile)
    acc, dismissed = _accepted(db, ctx.profile.id)
    b = PL.base_from(a, _goals(db, ctx.profile.id))
    cand = next((c for c in PL.candidate_actions(b) if c["code"] == code), None)
    taken = next((x for x in acc if x["source_code"] == code), None)
    if cand is None and taken is None:
        raise HTTPException(404, "No such action for this profile.")
    item = {**(cand or {}), **({"kind": taken["kind"], "params": taken["params"], "title": taken["title"]} if taken else {})}
    baseline, scen = PL.evaluate(b, []), PL.evaluate(b, [item])
    return {"action": item, "status": "accepted" if taken else "dismissed" if code in dismissed else "open",
            "baseline": baseline, "scenario": scen, "effect": PL.compare(baseline, scen),
            "impact": PL.headline_impact(item["kind"], item["params"], PL.compare(baseline, scen)),
            "method": PL.build(a, [], [], set())["method"], "history_untouched": True}


@router.post("/profiles/{internal_id}/plan/preview", summary="What-if: evaluate assumptions without saving anything")
def preview(body: PreviewIn, ctx: ProfileCtx = Depends(profile_reader), db: Session = Depends(get_db)):
    a = common.get_analysis(db, ctx.profile)
    items = [{"kind": x.kind, "params": _validate(db, ctx.profile.id, a, x.kind, x.params)} for x in body.assumptions]
    acc, _ = _accepted(db, ctx.profile.id)
    if body.include_accepted:
        replaced = {x.source_code for x in body.assumptions if x.source_code}
        items = [x for x in acc if x["source_code"] not in replaced] + items
    b = PL.base_from(a, _goals(db, ctx.profile.id))
    baseline, scen = PL.evaluate(b, []), PL.evaluate(b, items)
    effect = PL.compare(baseline, scen)
    single = PL.headline_impact(body.assumptions[0].kind, {}, PL.compare(baseline, PL.evaluate(b, items[-1:]))) \
        if len(body.assumptions) == 1 else None
    return {"baseline": PL._metrics(baseline), "scenario": PL._metrics(scen), "effect": effect, "impact": single,
            "over_committed": None if scen["surplus"] is None else scen["surplus"] < 0}


@router.post("/profiles/{internal_id}/plan/assumptions", status_code=201, summary="Accept an action into the plan")
def accept(body: AssumptionIn, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    a = common.get_analysis(db, ctx.profile)
    params = _validate(db, ctx.profile.id, a, body.kind, body.params)
    if body.source_code:
        db.execute(delete(M.PlanAssumption).where(M.PlanAssumption.user_id == ctx.profile.id,
                                                  M.PlanAssumption.source_code == body.source_code))
    row = M.PlanAssumption(user_id=ctx.profile.id, app_user_id=ctx.account.id, kind=body.kind, params=params,
                           title=PL.title_for(body.kind, params, _goal_name(db, params))[:160], source_code=body.source_code,
                           status="accepted")
    db.add(row)
    db.commit()
    audit(db, "plan.accept", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id,
          detail={"assumption_id": row.id, "kind": body.kind, "source_code": body.source_code})
    return {"id": row.id, "plan": _plan(db, ctx)}


@router.patch("/profiles/{internal_id}/plan/assumptions/{aid}", summary="Edit an accepted assumption")
def edit(aid: int, body: AssumptionPatch, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    row = db.get(M.PlanAssumption, aid)
    if row is None or row.user_id != ctx.profile.id or row.status != "accepted":
        raise HTTPException(404, "Assumption not found.")
    row.params = _validate(db, ctx.profile.id, common.get_analysis(db, ctx.profile), row.kind, {**row.params, **body.params})
    row.title = PL.title_for(row.kind, row.params, _goal_name(db, row.params))[:160]
    db.commit()
    audit(db, "plan.edit", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id,
          detail={"assumption_id": aid, "fields": sorted(body.params)})
    return {"id": row.id, "plan": _plan(db, ctx)}


@router.delete("/profiles/{internal_id}/plan/assumptions/{aid}", summary="Remove an assumption from the plan")
def remove(aid: int, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    row = db.get(M.PlanAssumption, aid)
    if row is None or row.user_id != ctx.profile.id:
        raise HTTPException(404, "Assumption not found.")
    db.delete(row)
    db.commit()
    audit(db, "plan.remove", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, detail={"assumption_id": aid})
    return {"removed": aid, "plan": _plan(db, ctx)}


@router.post("/profiles/{internal_id}/plan/dismiss", summary="Dismiss an action")
def dismiss(body: DismissIn, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    db.execute(delete(M.PlanAssumption).where(M.PlanAssumption.user_id == ctx.profile.id, M.PlanAssumption.source_code == body.code))
    db.add(M.PlanAssumption(user_id=ctx.profile.id, app_user_id=ctx.account.id, kind="dismissed", params={}, title="Dismissed",
                            source_code=body.code, status="dismissed"))
    db.commit()
    audit(db, "plan.dismiss", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, detail={"code": body.code})
    return {"dismissed": body.code, "plan": _plan(db, ctx)}


@router.delete("/profiles/{internal_id}/plan/dismiss/{code}", summary="Bring a dismissed action back")
def restore(code: str, request: Request, ctx: ProfileCtx = Depends(profile_writer), db: Session = Depends(get_db)):
    n = db.execute(delete(M.PlanAssumption).where(M.PlanAssumption.user_id == ctx.profile.id, M.PlanAssumption.source_code == code,
                                                  M.PlanAssumption.status == "dismissed")).rowcount
    db.commit()
    if not n:
        raise HTTPException(404, "That action is not dismissed.")
    audit(db, "plan.restore", request=request, app_user_id=ctx.account.id, profile_id=ctx.profile.id, detail={"code": code})
    return {"restored": code, "plan": _plan(db, ctx)}

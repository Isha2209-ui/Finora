"""FIRE planner, Decision Simulator, tax, debt payoff and the AI CFO."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as M
from .. import schemas as S
from ..cfo import agent, llm
from ..database import get_db
from ..services import calculations as C
from ..services import decision as D
from ..services import fire as F
from ..services import tax as T
from ..services.loader import load_identity
from . import common

router = APIRouter(prefix="/api", tags=["Planning & AI CFO"])


@router.post("/profiles/{internal_id}/fire", summary="FIRE projection with what-if inputs")
def fire(internal_id: str, body: S.FireIn, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    base = common.get_analysis(db, user)["fire"]
    fi = base["inputs"]
    pick = lambda v, d: d if v is None else v  # noqa: E731
    res = F.project(pick(body.current_corpus, fi["current_corpus"]), pick(body.monthly_investment, fi["monthly_investment"]),
                    fi["age"], pick(body.annual_expenses, fi["annual_expenses"]),
                    retirement_age_target=pick(body.retirement_age, user.retirement_age_target),
                    nominal_return=pick(body.nominal_return_pct, fi["nominal_return_pct"]) / 100,
                    inflation=pick(body.inflation_pct, fi["inflation_pct"]) / 100,
                    swr=pick(body.withdrawal_rate_pct, fi["withdrawal_rate_pct"]) / 100,
                    step_up=pick(body.step_up_pct, fi["annual_step_up_pct"]) / 100)
    res["baseline"] = {k: base[k] for k in ["fire_age", "fire_number", "success_probability_pct", "corpus_at_target_age"]}
    res["corpus_by_age"] = F.corpus_by_age(res["inputs"]["current_corpus"], res["inputs"]["monthly_investment"], fi["age"],
                                           [a for a in (35, 40, 45, 50, 55, 60, 65) if a > fi["age"]],
                                           nominal_return=res["inputs"]["nominal_return_pct"] / 100,
                                           inflation=res["inputs"]["inflation_pct"] / 100, step_up=res["inputs"]["annual_step_up_pct"] / 100)
    res["runway"] = common.get_analysis(db, user)["liquidity"]
    res["corpus_definition"], res["expense_definition"] = base["corpus_definition"], base["expense_definition"]
    return res


@router.post("/profiles/{internal_id}/decision", summary="Decision Simulator: should I make this purchase?")
def decision(internal_id: str, body: S.DecisionIn, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    return D.simulate(load_identity(db, user.id), snap=common.get_analysis(db, user), **body.model_dump())


@router.post("/tax/compare", summary="Old vs new regime (FY 2026-27)")
def tax_compare(body: S.TaxIn):
    d = body.model_dump()
    return T.compare(d.pop("gross_income"), d.pop("salaried"), **d)


@router.post("/profiles/{internal_id}/payoff", summary="Debt payoff plan with an extra monthly payment")
def payoff(internal_id: str, body: S.PayoffIn, db: Session = Depends(get_db)):
    a = common.get_analysis(db, common.get_user(db, internal_id))
    debts = [{"name": d["name"], "balance": d["balance"], "rate": d["rate"], "payment": d["payment"]} for d in a["debt"].get("debts", [])]
    if not debts:
        return {"has_debt": False}
    base = C.payoff_strategies(debts, 0.0)
    plan = C.payoff_strategies(debts, body.extra_monthly)
    return {"has_debt": True, "debts": debts, **plan,
            "vs_no_extra": {"months_saved": base["avalanche"]["months_to_debt_free"] - plan["avalanche"]["months_to_debt_free"],
                            "interest_saved": base["avalanche"]["total_interest"] - plan["avalanche"]["total_interest"]}}


# ---------------------------------------------------------------- AI CFO
@router.get("/cfo/status", summary="Is the local language model available?")
def cfo_status():
    return llm.status(force=True)


@router.post("/profiles/{internal_id}/chat", summary="Ask the AI CFO a question")
def chat(internal_id: str, body: S.ChatIn, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    hist = [{"role": m.role, "content": m.content} for m in db.scalars(
        select(M.ChatMessage).where(M.ChatMessage.user_id == user.id).order_by(M.ChatMessage.id.desc()).limit(6)).all()][::-1]
    res = agent.answer(body.message, common.cfo_context(db, user), hist, use_llm=body.use_llm)
    db.add(M.ChatMessage(user_id=user.id, role="user", content=body.message))
    db.add(M.ChatMessage(user_id=user.id, role="assistant", content=res["answer"],
                         meta={"engine": res["engine"], "tools_used": res.get("tools_used", [])}))
    db.commit()
    return res


@router.get("/profiles/{internal_id}/chat", summary="Chat history")
def chat_history(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    return [{"role": m.role, "content": m.content, "meta": m.meta, "at": m.created_at.isoformat()} for m in
            db.scalars(select(M.ChatMessage).where(M.ChatMessage.user_id == user.id).order_by(M.ChatMessage.id)).all()]


@router.delete("/profiles/{internal_id}/chat", summary="Clear chat history")
def clear_chat(internal_id: str, db: Session = Depends(get_db)):
    user = common.get_user(db, internal_id)
    db.execute(delete(M.ChatMessage).where(M.ChatMessage.user_id == user.id))
    db.commit()
    return {"cleared": True}


@router.get("/profiles/{internal_id}/briefing", summary="Monthly CFO briefing")
def briefing(internal_id: str, use_llm: bool = True, db: Session = Depends(get_db)):
    return agent.briefing(common.cfo_context(db, common.get_user(db, internal_id)), use_llm=use_llm)

"""Request bodies (Pydantic) for the Finora API."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LookupIn(BaseModel):
    pan: str = Field(..., description="Demo PAN-like identifier, e.g. ABCDE1234F")


class FireIn(BaseModel):
    monthly_investment: float | None = Field(None, ge=0)
    retirement_age: int | None = Field(None, ge=30, le=75)
    annual_expenses: float | None = Field(None, gt=0)
    nominal_return_pct: float | None = Field(None, ge=1, le=20)
    inflation_pct: float | None = Field(None, ge=0, le=15)
    withdrawal_rate_pct: float | None = Field(None, ge=2, le=6)
    step_up_pct: float | None = Field(None, ge=0, le=25)
    current_corpus: float | None = Field(None, ge=0)


class DecisionIn(BaseModel):
    item_type: str = "other"
    item_name: str = "Purchase"
    price: float = Field(..., gt=0)
    down_payment: float = Field(0, ge=0)
    interest_rate: float = Field(10.0, ge=0, le=40)
    tenure_months: int = Field(36, ge=0, le=360)
    running_cost_monthly: float | None = Field(None, ge=0)


class TaxIn(BaseModel):
    gross_income: float = Field(..., gt=0)
    salaried: bool = True
    sec_80c: float = Field(0, ge=0)
    sec_80d: float = Field(0, ge=0)
    home_loan_interest: float = Field(0, ge=0)
    hra_exemption: float = Field(0, ge=0)
    other: float = Field(0, ge=0)


class PayoffIn(BaseModel):
    extra_monthly: float = Field(0, ge=0)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=600)
    use_llm: bool = True


class CategoryPatch(BaseModel):
    category: str


class TransactionIn(BaseModel):
    date: date
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=2, max_length=200)
    type: Literal["debit", "credit"] = "debit"
    category: str | None = None
    account_id: int | None = None
    card_id: int | None = None


class ProfileIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    pan: str
    age: int = Field(..., ge=18, le=80)
    occupation: str = "Professional"
    employment_type: Literal["salaried", "self_employed"] = "salaried"
    city: str = "Jaipur"
    retirement_age_target: int = Field(60, ge=30, le=75)
    monthly_income: float = Field(..., gt=0)
    bank_name: str = "HDFC Bank"
    bank_balance: float = Field(0, ge=0)


class ProfilePatch(BaseModel):
    age: int | None = Field(None, ge=18, le=80)
    retirement_age_target: int | None = Field(None, ge=30, le=75)
    occupation: str | None = None
    city: str | None = None


class RecStatus(BaseModel):
    status: Literal["open", "accepted", "dismissed"]

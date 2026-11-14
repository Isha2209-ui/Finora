"""Request bodies (Pydantic) for the Finora API."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LookupIn(BaseModel):
    pan: str = Field(..., description="Demo PAN-like identifier, e.g. ABCDE1234F")


class ExploreIn(BaseModel):
    template_id: str = Field(..., max_length=32)


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


class SuggestionDecision(BaseModel):
    action: Literal["accept", "reject"]


class TransactionIn(BaseModel):
    date: date
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=2, max_length=200)
    type: Literal["debit", "credit"] = "debit"
    category: str | None = None
    account_id: int | None = None
    card_id: int | None = None


class ProfileIn(BaseModel):
    """A new private profile starts with personal details only. Nothing financial is invented: accounts, income,
    transactions and holdings are added afterwards by the person (manual entry or statement upload)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=120)
    pan: str | None = Field(None, description="Optional. Stored masked for display only; never used to look anything up.")
    age: int = Field(..., ge=18, le=80)
    occupation: str = Field("Professional", min_length=1, max_length=120)
    employment_type: Literal["salaried", "self_employed"] = "salaried"
    city: str = Field("Not specified", min_length=1, max_length=80)
    retirement_age_target: int = Field(60, ge=30, le=75)


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(None, min_length=2, max_length=120)
    age: int | None = Field(None, ge=18, le=80)
    retirement_age_target: int | None = Field(None, ge=30, le=75)
    occupation: str | None = Field(None, min_length=1, max_length=120)
    employment_type: Literal["salaried", "self_employed"] | None = None
    city: str | None = Field(None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def _ages(self):
        if self.age is not None and self.retirement_age_target is not None and self.retirement_age_target <= self.age:
            raise ValueError("Target retirement age must be above your current age.")
        return self


class RecStatus(BaseModel):
    status: Literal["open", "accepted", "dismissed"]

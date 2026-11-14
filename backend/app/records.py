"""Manual entry for every part of a financial identity, on top of the EXISTING tables.

Each record type maps to one existing SQLAlchemy model - no parallel or duplicate tables - so whatever a person types
here is read by the same loader -> snapshot -> models -> recommendations pipeline as the demo identities.

A record type declares: the model, a Pydantic schema (field rules + cross-field rules), which fields reference other
records of the same profile (checked for ownership), how to show a record, and field metadata the frontend uses to
build its forms. Writes are validated on the merged record, so a PATCH cannot sneak past a cross-field rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import models as M
from .config import AS_OF_DATE
from .services.cleaning import ALL_CATEGORIES

TODAY = date.fromisoformat(AS_OF_DATE)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _not_future(v: date | None, what: str = "Date") -> date | None:
    if v is not None and v > TODAY:
        raise ValueError(f"{what} cannot be in the future (today is {TODAY.isoformat()}).")
    return v


# ---------------------------------------------------------------- schemas (create = full record)
class BankAccountIn(_In):
    bank_name: str = Field(..., min_length=2, max_length=60)
    account_type: Literal["savings", "salary", "current"] = "savings"
    last4: str = Field(..., pattern=r"^\d{4}$", description="Last four digits only - never the full account number")
    balance: float = Field(..., ge=0, le=1e10)
    interest_rate: float = Field(3.0, ge=0, le=15)
    is_primary: bool = False


class CreditCardIn(_In):
    issuer: str = Field(..., min_length=2, max_length=60)
    card_name: str = Field(..., min_length=1, max_length=80)
    last4: str = Field(..., pattern=r"^\d{4}$", description="Last four digits only - never the full card number")
    credit_limit: float = Field(..., gt=0, le=1e8)
    outstanding: float = Field(0, ge=0, le=1e8)
    min_due: float = Field(0, ge=0, le=1e8)
    due_day: int = Field(..., ge=1, le=31)
    apr: float = Field(42.0, ge=0, le=60, description="Annual interest rate, %")

    @model_validator(mode="after")
    def _check(self):
        if self.min_due > self.outstanding:
            raise ValueError("Minimum due cannot be more than the outstanding balance.")
        if self.outstanding > self.credit_limit * 1.5:
            raise ValueError("Outstanding is far above the credit limit - please check the numbers.")
        return self


LOAN_TYPES = ["Home Loan", "Car Loan", "Two-wheeler Loan", "Personal Loan", "Education Loan", "Gold Loan", "Business Loan",
              "Consumer Durable Loan", "Other Loan"]


class LoanIn(_In):
    loan_type: Literal[tuple(LOAN_TYPES)] = "Personal Loan"  # type: ignore[valid-type]
    lender: str = Field(..., min_length=2, max_length=60)
    principal: float = Field(..., gt=0, le=1e10)
    balance: float = Field(..., ge=0, le=1e10)
    emi: float = Field(..., gt=0, le=1e8)
    interest_rate: float = Field(..., ge=0, le=40)
    tenure_months: int = Field(..., ge=1, le=480)
    remaining_months: int = Field(..., ge=0, le=480)
    property_id: int | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.remaining_months > self.tenure_months:
            raise ValueError("Remaining months cannot exceed the total tenure.")
        if self.balance > self.principal * 1.25:
            raise ValueError("Outstanding balance is far above the amount borrowed - please check.")
        if self.balance > 0 and self.remaining_months == 0:
            raise ValueError("A loan with a balance must have remaining months.")
        return self


class InsuranceIn(_In):
    kind: Literal["term", "health", "endowment"]
    insurer: str = Field(..., min_length=2, max_length=60)
    cover: float = Field(..., gt=0, le=1e11)
    annual_premium: float = Field(0, ge=0, le=1e8)


class StockIn(_In):
    symbol: str = Field(..., min_length=1, max_length=20)
    company: str = Field(..., min_length=1, max_length=80)
    sector: str = Field("Other", min_length=1, max_length=40)
    quantity: float = Field(..., gt=0, le=1e9)
    avg_buy_price: float = Field(..., gt=0, le=1e7)
    current_price: float = Field(..., gt=0, le=1e7)
    buy_date: date

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v):
        v = v.upper()
        if not re.fullmatch(r"[A-Z0-9&.\-]{1,20}", v):
            raise ValueError("Use the exchange symbol, e.g. INFY or M&M.")
        return v

    _d = field_validator("buy_date")(classmethod(lambda cls, v: _not_future(v, "Buy date")))


class MutualFundIn(_In):
    scheme: str = Field(..., min_length=2, max_length=120)
    fund_type: Literal["equity", "debt", "hybrid", "index", "elss"] = "equity"
    units: float = Field(..., gt=0, le=1e9)
    avg_nav: float = Field(..., gt=0, le=1e6)
    current_nav: float = Field(..., gt=0, le=1e6)
    start_date: date
    _d = field_validator("start_date")(classmethod(lambda cls, v: _not_future(v, "Start date")))


class SIPIn(_In):
    scheme: str = Field(..., min_length=2, max_length=120)
    amount: float = Field(..., gt=0, le=1e7)
    sip_day: int = Field(..., ge=1, le=28)
    start_date: date
    status: Literal["active", "paused", "stopped"] = "active"
    missed_last_12m: int = Field(0, ge=0, le=12)


class DepositIn(_In):
    kind: Literal["FD", "RD"] = "FD"
    bank: str = Field(..., min_length=2, max_length=60)
    principal: float = Field(..., gt=0, le=1e10, description="FD: amount deposited. RD: total deposited so far.")
    interest_rate: float = Field(..., ge=0, le=15)
    start_date: date
    maturity_date: date

    @model_validator(mode="after")
    def _check(self):
        _not_future(self.start_date, "Start date")
        if self.maturity_date <= self.start_date:
            raise ValueError("Maturity date must be after the start date.")
        return self


OTHER_KINDS = {"gold": "semi_liquid", "ppf": "locked", "epf": "locked", "nps": "locked", "bonds": "semi_liquid",
               "crypto": "liquid", "cash": "liquid"}


class OtherAssetIn(_In):
    kind: Literal["gold", "ppf", "epf", "nps", "bonds", "crypto", "cash"]
    description: str = Field("", max_length=120)
    value: float = Field(..., ge=0, le=1e11)
    liquidity: Literal["liquid", "semi_liquid", "locked"] | None = None

    @model_validator(mode="after")
    def _defaults(self):
        if self.liquidity is None:
            self.liquidity = OTHER_KINDS[self.kind]
        if not self.description:
            self.description = {"ppf": "PPF", "epf": "EPF", "nps": "NPS"}.get(self.kind, self.kind.title())
        return self


class PropertyIn(_In):
    kind: Literal["Apartment", "House", "Plot", "Commercial"] = "Apartment"
    city: str = Field(..., min_length=2, max_length=80)
    purchase_value: float = Field(..., gt=0, le=1e11)
    purchase_date: date
    current_value: float = Field(..., ge=0, le=1e11)
    monthly_rent: float = Field(0, ge=0, le=1e8)
    is_self_occupied: bool = True
    _d = field_validator("purchase_date")(classmethod(lambda cls, v: _not_future(v, "Purchase date")))

    @model_validator(mode="after")
    def _check(self):
        if self.is_self_occupied and self.monthly_rent > 0:
            raise ValueError("A self-occupied property does not earn rent. Untick 'self-occupied' to record rent.")
        return self


class GoalIn(_In):
    name: str = Field(..., min_length=2, max_length=80)
    target_amount: float = Field(..., gt=0, le=1e11)
    target_date: date
    current_amount: float = Field(0, ge=0, le=1e11)

    @model_validator(mode="after")
    def _check(self):
        if self.target_date <= TODAY:
            raise ValueError("Target date must be in the future.")
        return self


class IncomeIn(_In):
    amount: float = Field(..., gt=0, le=1e9)
    source: str = Field("Salary", min_length=2, max_length=80)
    date: date
    account_id: int | None = None
    _d = field_validator("date")(classmethod(lambda cls, v: _not_future(v, "Income date")))


class RecurringIn(_In):
    name: str = Field(..., min_length=2, max_length=80)
    category: str
    amount: float = Field(..., gt=0, le=1e8)
    frequency: Literal["monthly", "quarterly", "yearly"] = "monthly"
    day_of_month: int = Field(5, ge=1, le=28)

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v not in ALL_CATEGORIES:
            raise ValueError(f"Choose one of: {', '.join(ALL_CATEGORIES)}")
        return v


class TransactionIn(_In):
    date: date
    amount: float = Field(..., gt=0, le=1e9)
    description: str = Field(..., min_length=2, max_length=200)
    type: Literal["debit", "credit"] = "debit"
    category: str | None = None
    account_id: int | None = None
    card_id: int | None = None
    _d = field_validator("date")(classmethod(lambda cls, v: _not_future(v, "Transaction date")))

    @model_validator(mode="after")
    def _check(self):
        if self.account_id and self.card_id:
            raise ValueError("A transaction belongs to either a bank account or a card, not both.")
        if self.category is not None and self.category not in ALL_CATEGORIES:
            raise ValueError(f"Unknown category. Choose one of: {', '.join(ALL_CATEGORIES)}")
        return self


# ---------------------------------------------------------------- registry
@dataclass
class RecordType:
    key: str
    label: str
    model: type
    schema: type[_In]
    group: str
    refs: dict[str, type] = field(default_factory=dict)        # field -> model it must belong to (same profile)
    # DB column <-> API field translation (e.g. account_masked <-> last4)
    to_db: callable = None
    from_db: callable = None
    title: callable = None
    affects: str = ""


def _acct_to_db(d):
    d = dict(d)
    if "last4" in d:
        d["account_masked"] = "XXXX" + d.pop("last4")
    return d


def _acct_from_db(r):
    out = {c.key: getattr(r, c.key) for c in r.__table__.columns if c.key not in ("user_id", "account_masked")}
    out["last4"] = (r.account_masked or "")[-4:]
    return out


def _txn_to_db(d):
    d = dict(d)
    if "description" in d:
        d["raw_description"] = d.pop("description")
    return d


def _txn_from_db(r):
    out = {c.key: getattr(r, c.key) for c in r.__table__.columns
           if c.key not in ("user_id", "raw_description", "injected_anomaly_label")}
    out["description"] = r.raw_description
    return out


RECORD_TYPES: dict[str, RecordType] = {t.key: t for t in [
    RecordType("bank_accounts", "Bank accounts", M.BankAccount, BankAccountIn, "Accounts", to_db=_acct_to_db, from_db=_acct_from_db,
               title=lambda r: f"{r.bank_name} {r.account_type} ••{(r.account_masked or '')[-4:]}",
               affects="Net worth, emergency fund, runway, idle money"),
    RecordType("credit_cards", "Credit cards", M.CreditCard, CreditCardIn, "Accounts",
               title=lambda r: f"{r.issuer} {r.card_name} ••{r.last4}", affects="Liabilities, credit utilisation, credit-use pillar, debt plan"),
    RecordType("loans", "Loans", M.Loan, LoanIn, "Debt", refs={"property_id": M.Property},
               title=lambda r: f"{r.loan_type} ({r.lender})", affects="Liabilities, EMI load, debt-free date, Decision Simulator"),
    RecordType("insurance", "Insurance", M.InsurancePolicy, InsuranceIn, "Protection",
               title=lambda r: f"{r.kind.title()} - {r.insurer}", affects="Protection pillar, cover gaps"),
    RecordType("stocks", "Stocks", M.StockHolding, StockIn, "Investments",
               title=lambda r: f"{r.symbol} - {r.company}", affects="Net worth, allocation, FIRE corpus, concentration"),
    RecordType("mutual_funds", "Mutual funds", M.MutualFundHolding, MutualFundIn, "Investments",
               title=lambda r: r.scheme, affects="Net worth, allocation, FIRE corpus, liquidity"),
    RecordType("sips", "SIPs", M.SIP, SIPIn, "Investments",
               title=lambda r: f"{r.scheme} - {r.status}", affects="Investing pillar, FIRE monthly investment"),
    RecordType("deposits", "Fixed & recurring deposits", M.FixedDeposit, DepositIn, "Investments",
               title=lambda r: f"{r.kind} - {r.bank}", affects="Net worth, emergency pool, FIRE corpus"),
    RecordType("other_assets", "EPF, PPF, NPS, gold, bonds, crypto, cash", M.OtherAsset, OtherAssetIn, "Investments",
               title=lambda r: f"{r.kind.upper()} - {r.description}", affects="Net worth, allocation, FIRE corpus"),
    RecordType("properties", "Property", M.Property, PropertyIn, "Assets",
               title=lambda r: f"{r.kind}, {r.city}", affects="Net worth, real-estate share, FIRE corpus (if rented)"),
    RecordType("goals", "Goals", M.Goal, GoalIn, "Goals",
               title=lambda r: r.name, affects="Goal progress and monthly amount needed"),
    RecordType("income", "Income records", M.IncomeRecord, IncomeIn, "Cash flow", refs={"account_id": M.BankAccount},
               title=lambda r: f"{r.source} {r.date}", affects="Income, savings rate, tax estimate, debt load, forecast"),
    RecordType("recurring", "Recurring payments", M.RecurringPayment, RecurringIn, "Cash flow",
               title=lambda r: f"{r.name} ({r.frequency})", affects="Shown as known commitments (not counted as spending until paid)"),
    RecordType("transactions", "Transactions", M.Transaction, TransactionIn, "Cash flow",
               refs={"account_id": M.BankAccount, "card_id": M.CreditCard}, to_db=_txn_to_db, from_db=_txn_from_db,
               title=lambda r: f"{r.date} {r.raw_description[:40]}",
               affects="Spending, savings, budget, anomaly model, forecast model, FIRE expenses"),
]}


def field_meta(schema: type[_In]) -> list[dict]:
    """Describe a schema's fields for the frontend form builder (type, required, bounds, options, help)."""
    out = []
    for name, f in schema.model_fields.items():
        ann = f.annotation
        typ, options = "text", None
        args = getattr(ann, "__args__", ()) or ()
        origin = getattr(ann, "__origin__", None)
        base = [a for a in args if a is not type(None)] if args else [ann]
        b0 = base[0] if base else ann
        if getattr(b0, "__origin__", None) is Literal or origin is Literal:
            typ, options = "select", list(getattr(b0, "__args__", args))
        elif b0 is bool:
            typ = "checkbox"
        elif b0 in (int, float):
            typ = "number"
        elif b0 is date:
            typ = "date"
        if name == "category":
            typ, options = "select", ALL_CATEGORIES
        rule = {}
        for m in f.metadata:
            for k in ("ge", "gt", "le", "lt", "min_length", "max_length", "pattern"):
                if getattr(m, k, None) is not None:
                    rule[k] = getattr(m, k)
        default = None if f.is_required() else f.default
        out.append({"name": name, "type": typ, "required": f.is_required(), "default": default, "options": options,
                    "rules": rule, "help": f.description,
                    "ref": name if name in ("account_id", "card_id", "property_id") else None})
    return out

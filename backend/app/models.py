"""Finora database schema - a person's complete financial identity.

Two kinds of "user" exist and must not be confused:
  * AppUser (table app_users)  - a login account (email + password hash). Owns profiles.
  * User    (table users)      - a financial profile / identity. Every financial record belongs to a
                                 profile through users.id. Kept as "User" for backwards compatibility.

Profile kinds (users.kind):
  template   - one of the four read-only demo identities (synthetic). Never modified through the API.
  population - the synthetic population used only to train/evaluate models. Never reachable through the API.
  sandbox    - an editable copy of a template owned by one account, deleted after SANDBOX_TTL_HOURS.
  private    - a profile an account built itself. Only its owner can see it.

PAN is never stored in plain text: only a salted SHA-256 hash (for demo lookup) and a masked form.
"""
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _fk(table: str, nullable: bool = False):
    return mapped_column(ForeignKey(f"{table}.id", ondelete="CASCADE"), index=True, nullable=nullable)


# ---------------------------------------------------------------- login accounts & security
class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # stored lower-cased
    password_hash: Mapped[str] = mapped_column(String(255))  # argon2id (or bcrypt fallback); never the password
    display_name: Mapped[str] = mapped_column(String(80), default="")
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthSession(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 hash is stored."""
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_user_id: Mapped[int] = _fk("app_users")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str] = mapped_column(String(160), default="")


class AuditEvent(Base):
    """Security-relevant actions. Holds IDs and action names only - never PANs, passwords, tokens or raw statement data."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id", ondelete="SET NULL"), index=True, nullable=True)
    profile_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # no FK: survives profile deletion
    action: Mapped[str] = mapped_column(String(60), index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="ok")  # ok | denied | failed
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------- people & accounts
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    internal_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # FINORA_USER_001
    pan_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    pan_masked: Mapped[str | None] = mapped_column(String(10), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)
    occupation: Mapped[str] = mapped_column(String(120))
    employment_type: Mapped[str] = mapped_column(String(30))  # salaried | self_employed
    city: Mapped[str] = mapped_column(String(80))
    retirement_age_target: Mapped[int] = mapped_column(Integer, default=60)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Generator archetype - used ONLY to evaluate models afterwards, never as a model input.
    archetype: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Ownership (see module docstring). Templates and population profiles have no owner.
    kind: Mapped[str] = mapped_column(String(12), default="private", index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True, nullable=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # sandbox -> the template it was cloned from
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    bank_accounts = relationship("BankAccount", cascade="all, delete-orphan", passive_deletes=True)
    credit_cards = relationship("CreditCard", cascade="all, delete-orphan", passive_deletes=True)


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    bank_name: Mapped[str] = mapped_column(String(60))
    account_type: Mapped[str] = mapped_column(String(30))  # savings | salary | current
    account_masked: Mapped[str] = mapped_column(String(20))
    balance: Mapped[float] = mapped_column(Float)
    interest_rate: Mapped[float] = mapped_column(Float)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Where `balance` came from: "manual" (typed by the person / demo data) or "statement" (the closing running
    # balance of an imported statement that reconciled). A statement balance is a balance AS OF that date, not "today".
    balance_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    balance_source: Mapped[str | None] = mapped_column(String(20), nullable=True)


class CreditCard(Base):
    __tablename__ = "credit_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    issuer: Mapped[str] = mapped_column(String(60))
    card_name: Mapped[str] = mapped_column(String(80))
    last4: Mapped[str] = mapped_column(String(4))
    credit_limit: Mapped[float] = mapped_column(Float)
    outstanding: Mapped[float] = mapped_column(Float)
    min_due: Mapped[float] = mapped_column(Float)
    due_day: Mapped[int] = mapped_column(Integer)
    apr: Mapped[float] = mapped_column(Float)  # annual interest %


class CardStatement(Base):
    """Monthly statement per card - the input to the credit-risk model."""
    __tablename__ = "card_statements"
    __table_args__ = (UniqueConstraint("card_id", "month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = _fk("credit_cards")
    month: Mapped[str] = mapped_column(String(7))
    bill_amount: Mapped[float] = mapped_column(Float)
    paid_amount: Mapped[float] = mapped_column(Float)
    min_due: Mapped[float] = mapped_column(Float)
    # UCI convention: -2 no use, -1 paid in full, 0 revolving (min or more paid), 1..8 months delayed
    payment_status: Mapped[int] = mapped_column(Integer)


# ---------------------------------------------------------------- cash flow
class IncomeRecord(Base):
    __tablename__ = "income_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    account_id: Mapped[int | None] = _fk("bank_accounts", nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(80))  # Salary | Bonus | Client payment | Rent | Interest
    date: Mapped[date] = mapped_column(Date, index=True)
    # Statement-import provenance (NULL for demo data and manual entries)
    import_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    raw_description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    classified_by: Mapped[str | None] = mapped_column(String(40), nullable=True)  # rule name | user
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    account_id: Mapped[int | None] = _fk("bank_accounts", nullable=True)
    card_id: Mapped[int | None] = _fk("credit_cards", nullable=True)
    ref: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(10), default="debit")  # debit | credit
    raw_description: Mapped[str] = mapped_column(String(200))  # as it appears on the statement
    category: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    category_source: Mapped[str] = mapped_column(String(20), default="given")  # given | model | user
    merchant: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Ground-truth label for planted unusual transactions: evaluation ONLY, never a model input.
    injected_anomaly_label: Mapped[bool] = mapped_column(Boolean, default=False)
    # Statement-import provenance (NULL for demo data and manual entries)
    import_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    balance_after: Mapped[float | None] = mapped_column(Float, nullable=True)  # running balance printed on the statement
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # categoriser probability (category_source=model)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    flags: Mapped[str | None] = mapped_column(String(80), nullable=True)  # comma list: refund, transfer, possible_duplicate


class RecurringPayment(Base):
    __tablename__ = "recurring_payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Float)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    day_of_month: Mapped[int] = mapped_column(Integer, default=5)


# ---------------------------------------------------------------- investments & assets
class StockHolding(Base):
    __tablename__ = "stock_holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    symbol: Mapped[str] = mapped_column(String(20))
    company: Mapped[str] = mapped_column(String(80))
    sector: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[float] = mapped_column(Float)
    avg_buy_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    buy_date: Mapped[date] = mapped_column(Date)


class MutualFundHolding(Base):
    __tablename__ = "mutual_fund_holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    scheme: Mapped[str] = mapped_column(String(120))
    fund_type: Mapped[str] = mapped_column(String(30))  # equity | debt | hybrid | index | elss
    units: Mapped[float] = mapped_column(Float)
    avg_nav: Mapped[float] = mapped_column(Float)
    current_nav: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)


class SIP(Base):
    __tablename__ = "sips"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    scheme: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float)
    sip_day: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused | stopped
    missed_last_12m: Mapped[int] = mapped_column(Integer, default=0)


class FixedDeposit(Base):
    __tablename__ = "fixed_deposits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    bank: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(10), default="FD")  # FD | RD
    principal: Mapped[float] = mapped_column(Float)
    interest_rate: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date)


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    kind: Mapped[str] = mapped_column(String(40))  # Apartment | Plot | House
    city: Mapped[str] = mapped_column(String(80))
    purchase_value: Mapped[float] = mapped_column(Float)
    purchase_date: Mapped[date] = mapped_column(Date)
    current_value: Mapped[float] = mapped_column(Float)
    monthly_rent: Mapped[float] = mapped_column(Float, default=0.0)
    is_self_occupied: Mapped[bool] = mapped_column(Boolean, default=True)


class OtherAsset(Base):
    __tablename__ = "other_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    kind: Mapped[str] = mapped_column(String(20))  # gold | ppf | epf | nps | cash | crypto | bonds
    description: Mapped[str] = mapped_column(String(120))
    value: Mapped[float] = mapped_column(Float)
    liquidity: Mapped[str] = mapped_column(String(20))  # liquid | semi_liquid | locked


# ---------------------------------------------------------------- debt & protection
class Loan(Base):
    __tablename__ = "loans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    loan_type: Mapped[str] = mapped_column(String(40))
    lender: Mapped[str] = mapped_column(String(60))
    principal: Mapped[float] = mapped_column(Float)
    balance: Mapped[float] = mapped_column(Float)
    emi: Mapped[float] = mapped_column(Float)
    interest_rate: Mapped[float] = mapped_column(Float)
    tenure_months: Mapped[int] = mapped_column(Integer)
    remaining_months: Mapped[int] = mapped_column(Integer)
    property_id: Mapped[int | None] = _fk("properties", nullable=True)


class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    kind: Mapped[str] = mapped_column(String(20))  # term | health | endowment
    insurer: Mapped[str] = mapped_column(String(60))
    cover: Mapped[float] = mapped_column(Float)
    annual_premium: Mapped[float] = mapped_column(Float)


# ---------------------------------------------------------------- goals & history
class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    name: Mapped[str] = mapped_column(String(80))
    target_amount: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date] = mapped_column(Date)
    current_amount: Mapped[float] = mapped_column(Float, default=0.0)


class SavingsRecord(Base):
    __tablename__ = "savings_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    amount: Mapped[float] = mapped_column(Float)
    date: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(120), default="")


class MonthlySummary(Base):
    __tablename__ = "monthly_summaries"
    __table_args__ = (UniqueConstraint("user_id", "month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    month: Mapped[str] = mapped_column(String(7))
    income: Mapped[float] = mapped_column(Float)
    expenses: Mapped[float] = mapped_column(Float)
    savings: Mapped[float] = mapped_column(Float)


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    month: Mapped[str] = mapped_column(String(7))
    assets: Mapped[float] = mapped_column(Float)
    liabilities: Mapped[float] = mapped_column(Float)
    net_worth: Mapped[float] = mapped_column(Float)


# ---------------------------------------------------------------- results
class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    component: Mapped[str] = mapped_column(String(60))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    code: Mapped[str] = mapped_column(String(60))
    finding: Mapped[str] = mapped_column(String(240))
    evidence: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    impact_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | accepted | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    app_user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # who generated it
    report_path: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    app_user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # whose conversation
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------- statement imports
class StatementImport(Base):
    """One uploaded statement file: detection, mapping, progress, outcome and what is needed to undo it."""
    __tablename__ = "statement_imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    app_user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    filename: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="preview")  # preview|queued|running|done|failed|cancelled|undone
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    statement_kind: Mapped[str] = mapped_column(String(10), default="bank")  # bank | card
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detection: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # format, encoding, delimiter, header row, mapping
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_balance: Mapped[float | None] = mapped_column(Float, nullable=True)  # restored on undo
    previous_balance_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_balance_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # shared by every server process: liveness, cancellation and progress live in the database, not in one process's memory
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class CategoryRule(Base):
    """A correction the person made, remembered for future imports: narrations whose merchant key matches get this category."""
    __tablename__ = "category_rules"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _fk("users")
    merchant_key: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

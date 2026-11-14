"""Profile-level operations shared by routes and housekeeping: full deletion of a profile's data."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as M
from ..config import IMPORT_TMP_DIR, REPORTS_DIR

# Every table that hangs off users.id, children before parents.
PROFILE_TABLES = [M.PlanAssumption, M.StatementImport, M.CategoryRule, M.Transaction, M.IncomeRecord, M.RecurringPayment, M.StockHolding, M.MutualFundHolding, M.SIP, M.FixedDeposit,
                  M.OtherAsset, M.Loan, M.InsurancePolicy, M.Goal, M.SavingsRecord, M.MonthlySummary, M.NetWorthSnapshot,
                  M.AnalysisResult, M.Recommendation, M.Report, M.ChatMessage, M.Property, M.CreditCard, M.BankAccount]


def delete_profile_data(db: Session, profile: M.User) -> int:
    """Delete a profile, every row that belongs to it and its generated report files. Returns rows deleted.

    Refuses templates and population profiles: those are never deleted through the application.
    """
    if profile.kind not in ("sandbox", "private"):
        raise PermissionError("Only sandbox and private profiles can be deleted.")
    uid, n = profile.id, 0
    for (path,) in db.execute(select(M.Report.report_path).where(M.Report.user_id == uid)):
        p = Path(path)
        try:
            if p.resolve().parent == REPORTS_DIR.resolve() and p.exists():
                p.unlink()
        except OSError:
            pass
    for (imp_id,) in db.execute(select(M.StatementImport.id).where(M.StatementImport.user_id == uid)):
        try:
            (IMPORT_TMP_DIR / f"import_{imp_id}.csv").unlink(missing_ok=True)   # uploaded files still waiting in a preview
        except OSError:
            pass
    card_ids = [c for (c,) in db.execute(select(M.CreditCard.id).where(M.CreditCard.user_id == uid))]
    if card_ids:
        n += db.execute(delete(M.CardStatement).where(M.CardStatement.card_id.in_(card_ids))).rowcount or 0
    for model in PROFILE_TABLES:
        n += db.execute(delete(model).where(model.user_id == uid)).rowcount or 0
    db.delete(profile)
    return n + 1

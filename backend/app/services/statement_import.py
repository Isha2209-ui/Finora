"""Statement import pipeline: preview -> confirm -> background run (with progress) -> undo.

  1. preview   detect the layout from the file (encoding, delimiter, header row, column roles, date format, sign
               convention, running balance), show sample rows; the file waits in IMPORT_TMP_DIR, nothing is saved yet.
  2. confirm   the person can correct the column mapping, says whether it is a bank or card statement and which of their
               accounts/cards it belongs to (or creates one), and whether a verified closing balance may update the account.
  3. run       read -> parse (chunks) -> categorise with the trained model (chunks of distinct narrations) -> detect
               transfers/refunds/income -> drop rows already imported -> save in short chunks -> refresh the analysis.
               Progress is kept in memory per import and the stage in the database. Any failure removes what was saved.
  4. undo      deletes exactly the rows the import added and restores the previous account balance if it changed it.

Imported rows go into the same `transactions` / `income_records` tables as demo and manual data, so every page, model,
recommendation, forecast and report uses them with no special path.

Never invented: an account balance is only changed from a statement whose running balances reconcile, it is stored
with the date it applies to, and the person can decline it. Investment debits are reported as cash flows, never
turned into holdings.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from .. import models as M
from ..config import IMPORT_TMP_DIR, STATEMENT_MAX_ROWS
from ..data.generator import NON_EXPENSE
from ..database import SessionLocal
from ..ml import registry
from . import statement_parser as P
from .statement_classify import INCOME_CLASSES, classify

log = logging.getLogger("finora.import")
SAVE_CHUNK = 2000
STAGES = {"queued": (0, 1), "reading": (1, 6), "parsing": (6, 22), "categorising": (22, 60), "patterns": (60, 70),
          "duplicates": (70, 76), "saving": (76, 97), "analysis": (97, 100), "done": (100, 100)}
STAGE_LABEL = {"queued": "Waiting to start", "reading": "Reading the file", "parsing": "Reading dates, amounts and balances",
               "categorising": "Categorising with the ML model", "patterns": "Finding salary, transfers, refunds and card payments",
               "duplicates": "Skipping rows that are already imported", "saving": "Saving transactions",
               "analysis": "Refreshing your analysis", "done": "Finished"}
PROGRESS: dict[int, dict] = {}
CANCEL: set[int] = set()


class Cancelled(Exception):
    pass


def _progress(imp_id: int, stage: str, done: int = 0, total: int = 0) -> None:
    lo, hi = STAGES[stage]
    frac = (done / total) if total else 0.0
    PROGRESS[imp_id] = {"stage": stage, "label": STAGE_LABEL[stage], "done": done, "total": total,
                        "pct": round(lo + (hi - lo) * min(1.0, frac), 1), "at": time.time()}
    if imp_id in CANCEL:
        raise Cancelled()


def pending_path(imp_id: int):
    return IMPORT_TMP_DIR / f"import_{imp_id}.csv"


def norm_desc(s: str) -> str:
    return " ".join(str(s).upper().split())[:200]


# ---------------------------------------------------------------- 1. preview
def create_preview(db: Session, user: M.User, app_user_id: int | None, content: bytes, filename: str) -> M.StatementImport:
    det = P.detect(content)                                          # raises StatementError with a readable message
    imp = M.StatementImport(user_id=user.id, app_user_id=app_user_id, filename=filename[:120] or "statement.csv",
                            sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content), status="preview",
                            statement_kind=det["suggested_kind"], detection=det, rows_total=det["rows_in_file"])
    db.add(imp)
    db.flush()
    pending_path(imp.id).write_bytes(content)
    db.commit()
    return imp


def same_file_imports(db: Session, imp: M.StatementImport) -> list[dict]:
    q = select(M.StatementImport).where(M.StatementImport.user_id == imp.user_id, M.StatementImport.sha256 == imp.sha256,
                                        M.StatementImport.status == "done", M.StatementImport.id != imp.id)
    return [{"id": o.id, "filename": o.filename, "created_at": o.created_at.isoformat()} for o in db.scalars(q)]


# ---------------------------------------------------------------- 2. confirm
def configure(db: Session, user: M.User, imp: M.StatementImport, opts: dict) -> None:
    """Validate and store the person's choices; raises ValueError with a readable message."""
    if imp.status != "preview":
        raise ValueError(f"This import is already {imp.status}.")
    if not pending_path(imp.id).exists():
        raise ValueError("The uploaded file is no longer available. Please upload it again.")
    det = dict(imp.detection or {})
    headers = det.get("headers") or []
    mapping = opts.get("mapping")
    if mapping:
        idx = {}
        for role, colname in mapping.items():
            if colname in (None, ""):
                continue
            if role not in P.ROLES + ["balance_drcr"]:
                raise ValueError(f"Unknown column role '{role}'.")
            if colname not in headers:
                raise ValueError(f"Column '{colname}' is not in the file.")
            idx[role] = headers.index(colname)
        mapping_index = idx
        miss = P.missing_roles(mapping_index)
        if miss:
            raise ValueError("Map a column to: " + ", ".join(miss) + ".")
    else:
        mapping_index = {k: int(v) for k, v in (det.get("mapping_index") or {}).items()}
        if P.missing_roles(mapping_index):
            raise ValueError("Finora could not recognise this file's columns. Map a column to: " + ", ".join(P.missing_roles(mapping_index)) + ".")
    kind = opts.get("statement_kind") or imp.statement_kind
    if kind not in ("bank", "card"):
        raise ValueError("statement_kind must be 'bank' or 'card'.")
    account_id, card_id, new_account = opts.get("account_id"), opts.get("card_id"), opts.get("new_account")
    if account_id and card_id:
        raise ValueError("Choose either an account or a card, not both.")
    if account_id and db.scalar(select(M.BankAccount.user_id).where(M.BankAccount.id == account_id)) != user.id:
        raise ValueError("That account does not belong to this profile.")
    if card_id and db.scalar(select(M.CreditCard.user_id).where(M.CreditCard.id == card_id)) != user.id:
        raise ValueError("That card does not belong to this profile.")
    if kind == "card" and account_id:
        raise ValueError("A card statement must be attached to a card, not a bank account.")
    if kind == "bank" and card_id:
        raise ValueError("A bank statement must be attached to a bank account, not a card.")
    if new_account:
        if kind != "bank":
            raise ValueError("Only bank accounts can be created from a statement. Add the card under My Data first.")
        name = str(new_account.get("bank_name") or "").strip()
        last4 = str(new_account.get("last4") or "").strip()
        if not name or not (last4.isdigit() and len(last4) == 4):
            raise ValueError("A new account needs a bank name and the last 4 digits of the account number.")
        if new_account.get("balance") is not None:
            try:
                float(new_account["balance"])
            except (TypeError, ValueError):
                raise ValueError("The balance must be a number.")
    sign = opts.get("sign_convention")
    if sign not in (None, "negative_is_debit", "positive_is_debit"):
        raise ValueError("sign_convention must be negative_is_debit or positive_is_debit.")
    det["options"] = {"mapping_index": mapping_index, "sign_convention": sign, "date_format": opts.get("date_format"),
                      "update_balance": bool(opts.get("update_balance", True)), "new_account": new_account,
                      "allow_same_file": bool(opts.get("allow_same_file", False))}
    imp.detection = det
    imp.statement_kind, imp.account_id, imp.card_id = kind, account_id, card_id
    imp.status, imp.stage = "queued", "queued"
    db.commit()
    _progress(imp.id, "queued")


# ---------------------------------------------------------------- 3. run
def _history(db: Session, uid: int) -> pd.DataFrame:
    cols = [M.Transaction.id, M.Transaction.date, M.Transaction.amount, M.Transaction.type, M.Transaction.raw_description,
            M.Transaction.category, M.Transaction.account_id, M.Transaction.card_id, M.Transaction.import_id,
            M.Transaction.category_source]
    rows = db.execute(select(*cols).where(M.Transaction.user_id == uid)).all()
    return pd.DataFrame(rows, columns=[c.key for c in cols])


def run(imp_id: int) -> None:
    """Background worker. Uses its own session; commits in short chunks; cleans up after any failure."""
    db = SessionLocal()
    t0 = time.time()
    try:
        imp = db.get(M.StatementImport, imp_id)
        if imp is None or imp.status != "queued":
            return
        user = db.get(M.User, imp.user_id)
        opts = (imp.detection or {}).get("options", {})
        imp.status = "running"
        db.commit()
        _stage(db, imp, "reading")
        content = pending_path(imp.id).read_bytes()
        table = P.read_table(content, max_rows=STATEMENT_MAX_ROWS)
        _stage(db, imp, "parsing")
        parsed = P.parse(table, mapping={k: int(v) for k, v in opts["mapping_index"].items()}, kind=imp.statement_kind,
                         sign=opts.get("sign_convention"), date_format=opts.get("date_format"),
                         progress=lambda d, n: _progress(imp_id, "parsing", d, n))
        rows = parsed.rows
        if rows.empty:
            raise P.StatementError("No valid transactions were found in the file with this column mapping.")
        imp.rows_total = int(parsed.detection["rows_parsed"])
        # ---- the person's accounts, rules and history
        account_id, card_id = imp.account_id, imp.card_id
        accounts = db.scalars(select(M.BankAccount).where(M.BankAccount.user_id == user.id)).all()
        cards = db.scalars(select(M.CreditCard).where(M.CreditCard.user_id == user.id)).all()
        new_acc = opts.get("new_account")
        history = _history(db, user.id)
        rules = {r.merchant_key: r.category for r in db.scalars(select(M.CategoryRule).where(M.CategoryRule.user_id == user.id))}
        _stage(db, imp, "categorising")
        own_acc = {a.account_masked[-4:] for a in accounts if a.id != account_id and a.account_masked}
        own_cards = {c.last4 for c in cards if c.id != card_id and c.last4}
        target = ("card", card_id) if imp.statement_kind == "card" else ("account", account_id)
        rows, cstats = classify(rows, kind=imp.statement_kind, art=registry.get("categoriser"), rules=rules,
                                own_account_last4=own_acc, own_card_last4=own_cards, history=history, this_account=target,
                                progress=lambda d, n: _progress(imp_id, "categorising", d, n))
        _stage(db, imp, "patterns")
        # ---- duplicates: rows already in the database for the same account/card (counted, so genuine repeats survive)
        _stage(db, imp, "duplicates")
        if new_acc is None:
            existing = Counter()
            if imp.statement_kind == "card":
                same = history[history["card_id"] == card_id] if card_id else history[history["card_id"].isna() & history["account_id"].isna()]
            else:
                same = history[history["account_id"] == account_id] if account_id else history[history["card_id"].isna() & history["account_id"].isna()]
            for d, a, ty, ds in zip(same["date"], same["amount"], same["type"], same["raw_description"]):
                existing[(pd.Timestamp(d).date(), round(float(a), 2), ty, norm_desc(ds))] += 1
            inc_q = select(M.IncomeRecord.date, M.IncomeRecord.amount, M.IncomeRecord.raw_description).where(
                M.IncomeRecord.user_id == user.id, M.IncomeRecord.raw_description.is_not(None),
                (M.IncomeRecord.account_id == account_id) if account_id else M.IncomeRecord.account_id.is_(None))
            if imp.statement_kind == "bank":
                for d, a, ds in db.execute(inc_q):
                    existing[(d, round(float(a), 2), "credit", norm_desc(ds))] += 1
        else:
            existing = Counter()
        keys = [(d.date(), round(float(a), 2), ty, norm_desc(ds)) for d, a, ty, ds in
                zip(rows["date"], rows["amount"], rows["type"], rows["raw_description"])]
        dup = np.zeros(len(rows), bool)
        for i, k in enumerate(keys):
            if existing[k] > 0:
                existing[k] -= 1
                dup[i] = True
        # possible duplicates of hand-entered rows (same day, amount and direction, different text): kept, but flagged
        manual = history[history["import_id"].isna() & history["category_source"].isin(["user", "model", "given"])]
        possible = np.zeros(len(rows), bool)
        if len(manual):
            mk = {(pd.Timestamp(d).date(), round(float(a), 2), ty) for d, a, ty in zip(manual["date"], manual["amount"], manual["type"])}
            mkd = {(pd.Timestamp(d).date(), round(float(a), 2), ty, norm_desc(ds)) for d, a, ty, ds in
                   zip(manual["date"], manual["amount"], manual["type"], manual["raw_description"])}
            for i, k in enumerate(keys):
                if not dup[i] and k[:3] in mk and k not in mkd:
                    possible[i] = True
        rows = rows.assign(dup=dup)
        pos_idx = np.where(possible)[0]
        rows.loc[pos_idx, "needs_review"] = True
        rows.loc[pos_idx, "review_reason"] = "Same date, amount and direction as a transaction you entered by hand; delete one if it is a duplicate."
        rows.loc[pos_idx, "flags"] = (rows.loc[pos_idx, "flags"] + ",possible_duplicate").str.strip(",")
        new = rows[~rows["dup"]]
        # ---- account created from the statement (balance only from a verified statement or typed by the person)
        bal = parsed.detection.get("balance") or {}
        created_account = None
        if new_acc:
            typed = new_acc.get("balance")
            if typed is not None:
                start_bal, src, as_of = float(typed), "manual", None
            elif bal.get("verified"):
                start_bal, src, as_of = bal["closing_balance"], "statement", pd.Timestamp(bal["closing_date"]).date()
            else:
                raise P.StatementError("This statement has no running balance that reconciles, so Finora cannot know the account's "
                                       "balance. Enter the current balance for the new account, or attach the statement to an existing account.")
            created_account = M.BankAccount(user_id=user.id, bank_name=str(new_acc["bank_name"])[:60],
                                            account_type=str(new_acc.get("account_type") or "savings")[:30],
                                            account_masked="XXXX" + str(new_acc["last4"]), balance=start_bal,
                                            interest_rate=float(new_acc.get("interest_rate") or 0.0),
                                            is_primary=not accounts, balance_as_of=as_of, balance_source=src)
            db.add(created_account)
            db.flush()
            account_id = created_account.id
            imp.account_id = account_id
            db.commit()
        # ---- save in short chunks
        _stage(db, imp, "saving")
        tx_payload, inc_payload = [], []
        prefix = f"{user.internal_id[-6:]}-I{imp.id}-"
        n_tx = 0
        for r in new.itertuples(index=False):
            common = {"user_id": user.id, "date": r.date.date(), "amount": float(r.amount), "import_id": imp.id,
                      "confidence": None if pd.isna(r.confidence) else float(r.confidence), "needs_review": bool(r.needs_review),
                      "review_reason": (r.review_reason or None) and str(r.review_reason)[:160]}
            if r.target == "income":
                inc_payload.append({**common, "account_id": account_id if imp.statement_kind == "bank" else None,
                                    "source": r.income_source, "raw_description": r.raw_description[:200],
                                    "classified_by": r.category_source})
            else:
                n_tx += 1
                tx_payload.append({**common, "account_id": account_id if imp.statement_kind == "bank" else None,
                                   "card_id": card_id if imp.statement_kind == "card" else None, "ref": f"{prefix}{n_tx:06d}",
                                   "type": r.type, "raw_description": r.raw_description[:200], "category": r.category,
                                   "category_source": "model" if r.category_source == "model" else
                                   ("given" if r.category_source == "given" else r.category_source),
                                   "merchant": (r.merchant or None) and str(r.merchant)[:80],
                                   "balance_after": None if pd.isna(r.balance) else float(r.balance),
                                   "flags": r.flags or None, "injected_anomaly_label": False})
        total = len(tx_payload) + len(inc_payload)
        done = 0
        for model, payload in ((M.Transaction, tx_payload), (M.IncomeRecord, inc_payload)):
            for s in range(0, len(payload), SAVE_CHUNK):
                part = payload[s:s + SAVE_CHUNK]
                db.execute(insert(model), part)
                db.commit()
                done += len(part)
                _progress(imp_id, "saving", done, total)
        # ---- verified closing balance
        balance_out = {"present": bool(bal.get("present")), "verified": bool(bal.get("verified")),
                       "closing_balance": bal.get("closing_balance"), "closing_date": bal.get("closing_date"),
                       "reconciled_pct": bal.get("reconciled_pct"), "applied": False, "reason": bal.get("reason")}
        if imp.statement_kind == "card":
            balance_out["reason"] = ("Card statements do not carry a running balance; the card's outstanding amount was left as you entered it."
                                     if not bal.get("present") else balance_out["reason"])
        elif created_account is not None:
            balance_out["applied"] = created_account.balance_source == "statement"
            balance_out["reason"] = ("New account opened with the verified closing balance." if balance_out["applied"]
                                     else "New account opened with the balance you typed.")
        elif bal.get("verified") and account_id:
            acc = db.get(M.BankAccount, account_id)
            closing_date = pd.Timestamp(bal["closing_date"]).date()
            if not opts.get("update_balance", True):
                balance_out["reason"] = "You chose not to update the account balance from this statement."
            elif acc.balance_as_of and acc.balance_source == "statement" and acc.balance_as_of > closing_date:
                balance_out["reason"] = f"The account already has a newer verified balance (as of {acc.balance_as_of.isoformat()})."
            else:
                imp.previous_balance, imp.previous_balance_as_of = acc.balance, acc.balance_as_of
                imp.previous_balance_source = acc.balance_source or "manual"
                acc.balance, acc.balance_as_of, acc.balance_source = float(bal["closing_balance"]), closing_date, "statement"
                balance_out["applied"] = True
                balance_out["previous_balance"] = imp.previous_balance
                balance_out["reason"] = f"Account balance set to the verified closing balance as of {closing_date.isoformat()}."
        elif bal.get("present") and not account_id:
            balance_out["reason"] = "No account was selected, so no balance was updated."
        elif not bal.get("present"):
            balance_out["reason"] = "This file has no running balance, so Finora cannot establish a balance from it; the account balance was not changed."
        imp.summary = _summary(parsed, rows, new, dup, possible, cstats, balance_out, time.time() - t0, created_account)
        imp.rows_processed = int(len(rows))
        db.commit()
        # Recompute the whole analysis now (identity, cash flow, health, models, recommendations), so the next page the
        # person opens is already up to date. A failure here never undoes the import: the cache is just invalidated.
        _stage(db, imp, "analysis")
        from ..routes import common
        common.invalidate(user.id)
        ta = time.time()
        try:
            common.get_analysis(db, user, refresh=True)
            imp.summary = {**imp.summary, "analysis_seconds": round(time.time() - ta, 2)}
        except Exception:  # noqa: BLE001
            log.exception("analysis refresh after import %s failed", imp_id)
            common.invalidate(user.id)
        imp.status, imp.stage, imp.finished_at = "done", "done", datetime.utcnow()
        db.commit()
        _progress(imp_id, "done", 1, 1)
    except Exception as e:  # noqa: BLE001 - every failure must leave no partial import behind
        db.rollback()
        cancelled = isinstance(e, Cancelled)
        if not isinstance(e, (P.StatementError, Cancelled)):
            log.exception("statement import %s failed", imp_id)
        _cleanup_rows(db, imp_id)
        imp = db.get(M.StatementImport, imp_id)
        if imp is not None:
            if imp.summary is None and imp.account_id and (imp.detection or {}).get("options", {}).get("new_account"):
                acc = db.get(M.BankAccount, imp.account_id)
                if acc is not None:
                    db.delete(acc)
                    imp.account_id = None
            imp.status = "cancelled" if cancelled else "failed"
            imp.error = "Import cancelled; nothing was saved." if cancelled else (
                str(e) if isinstance(e, P.StatementError) else f"Unexpected error while importing ({type(e).__name__}). Nothing was saved.")
            imp.finished_at = datetime.utcnow()
            db.commit()
        PROGRESS.pop(imp_id, None)
    finally:
        CANCEL.discard(imp_id)
        try:
            pending_path(imp_id).unlink(missing_ok=True)
        except OSError:
            pass
        db.close()


def _stage(db: Session, imp: M.StatementImport, stage: str) -> None:
    imp.stage = stage
    db.commit()
    _progress(imp.id, stage)


def _cleanup_rows(db: Session, imp_id: int) -> None:
    db.execute(delete(M.Transaction).where(M.Transaction.import_id == imp_id))
    db.execute(delete(M.IncomeRecord).where(M.IncomeRecord.import_id == imp_id))
    db.commit()


def _summary(parsed, rows, new, dup, possible, cstats, balance, secs, created_account) -> dict:
    det = parsed.detection
    tx = new[new["target"] == "tx"]
    inc = new[new["target"] == "income"]
    flags = new["flags"].fillna("")
    deb = tx[tx["type"] == "debit"]
    return {
        "rows_in_file": det["rows_parsed"] + det["dropped"].get("wrong number of columns", 0), "rows_valid": int(len(rows)),
        "rows_dropped": int(sum(det["dropped"].values())), "dropped": det["dropped"], "warnings": det["warnings"],
        "layout": det["layout"], "layout_kind": det["layout_kind"], "date_format": det["date_format"],
        "date_from": det["date_from"], "date_to": det["date_to"], "months_covered": det["months_covered"],
        "transactions_added": int(len(tx)), "income_records_added": int(len(inc)), "duplicates_skipped": int(dup.sum()),
        "possible_duplicates": int(possible.sum()),
        "categorised_by_model": int((rows["category_source"] == "model").sum()),
        "distinct_narrations_scored": cstats["distinct_narrations_scored"], "decided_by": cstats["by_source"],
        "by_category": {k: int(v) for k, v in deb["category"].value_counts().items()},
        # spending only: card bills, own transfers and investments move money, they are not spent
        "spend_by_category": {k: round(float(v), 2) for k, v in deb[~deb["category"].isin(NON_EXPENSE)].groupby("category")["amount"].sum()
                              .sort_values(ascending=False).items()},
        "money_moved": {k: round(float(v), 2) for k, v in deb[deb["category"].isin(NON_EXPENSE)].groupby("category")["amount"].sum()
                        .sort_values(ascending=False).items()},
        "income_by_source": {k: round(float(v), 2) for k, v in inc.groupby("income_source")["amount"].sum().items()},
        "transfers": int(flags.str.contains("transfer").sum()), "refunds": int(flags.str.contains("refund").sum()),
        "card_payments": int(flags.str.contains("card_payment").sum()),
        "unrecognised_credits": int(flags.str.contains("unrecognised_credit").sum()),
        "investment_outflow": round(float(deb[deb["category"] == "Investment"]["amount"].sum()), 2),
        "investment_inflow": round(float(tx[(tx["type"] == "credit") & (tx["category"] == "Investment")]["amount"].sum()), 2),
        "needs_review": int(new["needs_review"].sum()),
        "low_confidence": [{"description": r.raw_description[:80], "predicted": r.category, "confidence": round(float(r.confidence), 3)}
                           for r in new[(new["category_source"] == "model") & new["needs_review"]].head(20).itertuples()],
        "balance": balance, "created_account_id": created_account.id if created_account is not None else None,
        "seconds": round(secs, 2), "rows_per_second": int(len(rows) / secs) if secs > 0 else None,
    }


# ---------------------------------------------------------------- 4. undo / cancel / housekeeping
def undo(db: Session, imp: M.StatementImport) -> dict:
    if imp.status != "done":
        raise ValueError(f"Only a finished import can be undone (this one is {imp.status}).")
    n_tx = db.execute(delete(M.Transaction).where(M.Transaction.import_id == imp.id)).rowcount or 0
    n_inc = db.execute(delete(M.IncomeRecord).where(M.IncomeRecord.import_id == imp.id)).rowcount or 0
    restored = False
    s = imp.summary or {}
    if imp.account_id and s.get("balance", {}).get("applied") and imp.previous_balance is not None:
        acc = db.get(M.BankAccount, imp.account_id)
        if acc is not None and acc.balance_source == "statement" and acc.balance_as_of and \
                acc.balance_as_of.isoformat() == s["balance"]["closing_date"]:
            acc.balance, acc.balance_as_of, acc.balance_source = imp.previous_balance, imp.previous_balance_as_of, imp.previous_balance_source
            restored = True
    removed_account = False
    if s.get("created_account_id"):
        acc = db.get(M.BankAccount, s["created_account_id"])
        still_used = db.scalar(select(M.Transaction.id).where(M.Transaction.account_id == s["created_account_id"]).limit(1))
        if acc is not None and not still_used:
            db.execute(delete(M.IncomeRecord).where(M.IncomeRecord.account_id == acc.id))
            db.delete(acc)
            removed_account = True
    imp.status = "undone"
    db.commit()
    return {"transactions_removed": n_tx, "income_records_removed": n_inc, "balance_restored": restored,
            "account_removed": removed_account}


def cancel(db: Session, imp: M.StatementImport) -> None:
    if imp.status == "preview":
        imp.status = "cancelled"
        pending_path(imp.id).unlink(missing_ok=True)
        db.commit()
    elif imp.status in ("queued", "running"):
        CANCEL.add(imp.id)
    else:
        raise ValueError(f"This import is already {imp.status}.")


def recover_interrupted(db: Session) -> int:
    """At start-up: imports left running by a stopped server are rolled back and marked failed; stale previews expire."""
    n = 0
    for imp in db.scalars(select(M.StatementImport).where(M.StatementImport.status.in_(["queued", "running"]))):
        _cleanup_rows(db, imp.id)
        imp.status, imp.error = "failed", "The server stopped during this import, so it was rolled back. Please import the file again."
        n += 1
    cutoff = datetime.utcnow().timestamp() - 24 * 3600
    for imp in db.scalars(select(M.StatementImport).where(M.StatementImport.status == "preview")):
        if imp.created_at.timestamp() < cutoff:
            imp.status = "cancelled"
            pending_path(imp.id).unlink(missing_ok=True)
    db.commit()
    return n


def status(imp: M.StatementImport) -> dict:
    live = PROGRESS.get(imp.id)
    pct = 100.0 if imp.status == "done" else (live["pct"] if live and imp.status in ("queued", "running") else 0.0)
    return {"id": imp.id, "filename": imp.filename, "status": imp.status, "stage": imp.stage,
            "stage_label": (live or {}).get("label") or STAGE_LABEL.get(imp.stage or "", None), "pct": pct,
            "stage_done": (live or {}).get("done"), "stage_total": (live or {}).get("total"),
            "statement_kind": imp.statement_kind, "account_id": imp.account_id, "card_id": imp.card_id,
            "rows_total": imp.rows_total, "size_bytes": imp.size_bytes, "summary": imp.summary, "error": imp.error,
            "created_at": imp.created_at.isoformat(), "finished_at": imp.finished_at.isoformat() if imp.finished_at else None}


# ---------------------------------------------------------------- legacy one-shot upload (/upload)
def import_statement(db: Session, user: M.User, content: bytes, account_id: int | None = None, card_id: int | None = None,
                     app_user_id: int | None = None, filename: str = "statement.csv") -> dict:
    """The original one-call upload, kept for compatibility: auto-detected mapping, no balance change, runs inline."""
    try:
        imp = create_preview(db, user, app_user_id, content, filename)
    except P.StatementError as e:
        raise ValueError(str(e))
    kind = "card" if card_id else ("bank" if account_id else imp.statement_kind)
    if kind == "card" and not card_id:
        kind = "bank"
    configure(db, user, imp, {"statement_kind": kind, "account_id": account_id if kind == "bank" else None,
                              "card_id": card_id, "update_balance": False})
    run(imp.id)
    db.expire_all()
    imp = db.get(M.StatementImport, imp.id)
    if imp.status != "done":
        raise ValueError(imp.error or "Import failed.")
    s = imp.summary
    return {**s, "import_id": imp.id, "note": "Low-confidence categories can be corrected in Statement Intelligence."}


INCOME_SOURCES = INCOME_CLASSES


def parse_csv(content: bytes) -> tuple[pd.DataFrame, dict]:
    """Compatibility wrapper (pre-Phase-4 API): parse with auto-detected mapping and return (rows, report)."""
    try:
        parsed = P.parse(P.read_table(content, max_rows=STATEMENT_MAX_ROWS))
    except P.StatementError as e:
        raise ValueError(str(e))
    det = parsed.detection
    layout = "debit/credit columns" if det["layout_kind"] == "separate debit and credit columns" else "single amount column"
    return parsed.rows, {"rows_in_file": det["rows_parsed"], "rows_valid": det["rows_valid"],
                         "rows_dropped": det["rows_parsed"] - det["rows_valid"], "layout": layout, "detection": det}

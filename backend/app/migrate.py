"""Small, additive schema migration for existing local databases (SQLite or PostgreSQL).

Finora has no Alembic history yet, so a database created before accounts existed is upgraded in place:
  1. new tables (app_users, auth_sessions, audit_events) are created;
  2. missing columns are added with ALTER TABLE ... ADD COLUMN (never dropped or rewritten);
  3. profile kinds are back-filled: demo identities -> template, training population -> population,
     older ownerless custom profiles -> private with no owner (unreachable until claimed or deleted).
It is idempotent and safe to run on every start.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .database import Base

# table -> [(column, SQL type, default SQL or None)]
_COLUMNS = {
    "users": [("kind", "VARCHAR(12)", "'private'"), ("owner_id", "INTEGER", None), ("template_id", "INTEGER", None),
              ("expires_at", "TIMESTAMP", None)],
    "reports": [("app_user_id", "INTEGER", None)],
    "chat_messages": [("app_user_id", "INTEGER", None)],
    # Phase 4: statement-import provenance
    "transactions": [("import_id", "INTEGER", None), ("balance_after", "FLOAT", None), ("confidence", "FLOAT", None),
                     ("needs_review", "BOOLEAN", "0"), ("review_reason", "VARCHAR(160)", None), ("flags", "VARCHAR(80)", None)],
    "income_records": [("import_id", "INTEGER", None), ("raw_description", "VARCHAR(200)", None),
                       ("classified_by", "VARCHAR(40)", None), ("confidence", "FLOAT", None), ("needs_review", "BOOLEAN", "0"),
                       ("review_reason", "VARCHAR(160)", None)],
    "bank_accounts": [("balance_as_of", "DATE", None), ("balance_source", "VARCHAR(20)", None)],
}


def run(engine: Engine) -> list[str]:
    from . import models  # noqa: F401  (register tables)

    done: list[str] = []
    Base.metadata.create_all(engine)  # creates only tables that do not exist yet
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _COLUMNS.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, typ, default in cols:
                if name in have:
                    continue
                ddl = f"ALTER TABLE {table} ADD COLUMN {name} {typ}" + (f" DEFAULT {default}" if default else "")
                conn.execute(text(ddl))
                done.append(f"{table}.{name}")
        if insp.has_table("users"):
            # Back-fill only rows that were never classified (older databases).
            r1 = conn.execute(text("UPDATE users SET kind='template' WHERE pan_hash IS NOT NULL AND archetype <> 'custom' "
                                   "AND owner_id IS NULL AND (kind IS NULL OR kind='private')"))
            r2 = conn.execute(text("UPDATE users SET kind='population' WHERE pan_hash IS NULL AND archetype <> 'custom' "
                                   "AND owner_id IS NULL AND (kind IS NULL OR kind='private')"))
            r3 = conn.execute(text("UPDATE users SET kind='private' WHERE kind IS NULL"))
            if r1.rowcount or r2.rowcount or r3.rowcount:
                done.append(f"users.kind backfill: template={r1.rowcount} population={r2.rowcount} other={r3.rowcount}")
    # indexes for the new columns (create_all does not add indexes to existing tables)
    with engine.begin() as conn:
        for stmt in ("CREATE INDEX IF NOT EXISTS ix_users_owner_id ON users (owner_id)",
                     "CREATE INDEX IF NOT EXISTS ix_users_kind ON users (kind)",
                     "CREATE INDEX IF NOT EXISTS ix_users_expires_at ON users (expires_at)",
                     "CREATE INDEX IF NOT EXISTS ix_chat_messages_app_user_id ON chat_messages (app_user_id)",
                     "CREATE INDEX IF NOT EXISTS ix_reports_app_user_id ON reports (app_user_id)",
                     "CREATE INDEX IF NOT EXISTS ix_transactions_import_id ON transactions (import_id)",
                     "CREATE INDEX IF NOT EXISTS ix_income_records_import_id ON income_records (import_id)"):
            try:
                conn.execute(text(stmt))
            except Exception:  # pragma: no cover - index already present under another name
                pass
    return done

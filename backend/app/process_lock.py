"""One server process per database.

Finora keeps some import state (the per-profile import lock, live progress) in the server process, and its start-up
recovery assumes that no other process is working on the same database. So exactly ONE server process may serve a given
SQLite database. At start-up the server takes an exclusive OS lock on `<database>.lock`; a second process (another
uvicorn, or `--workers 2`) pointed at the same database refuses to start instead of recovering or modifying imports that
belong to the first. The OS releases the lock automatically when the process exits, including after a crash.

This is a restriction, not distributed multi-process support. For PostgreSQL deployments the same rule applies and is
documented (one application process), but no file lock is taken.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

_held: dict[str, object] = {}


class SecondProcessError(RuntimeError):
    pass


def sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url[len("sqlite:///"):])


def acquire(database_url: str) -> Path | None:
    """Take the exclusive lock for this database, or raise SecondProcessError. Idempotent within one process."""
    db = sqlite_path(database_url)
    if db is None:
        return None
    lock_path = db.with_name(db.name + ".lock")
    key = str(lock_path)
    if key in _held:
        return lock_path
    fh = open(lock_path, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise SecondProcessError(
            f"Another Finora server process is already using {db.name}. Only one server process may run against a "
            "database (run uvicorn without --workers, and stop the other server first).")
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _held[key] = fh
    return lock_path


def release_all() -> None:
    for fh in _held.values():
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()
        except OSError:
            pass
    _held.clear()

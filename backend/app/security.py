"""Security primitives: password hashing, session tokens, rate limiting and log scrubbing.

* Passwords: argon2id (argon2-cffi). If argon2 cannot be imported, bcrypt is used instead. Hashes are
  self-describing, so a database can contain both and verification picks the right one.
* Session tokens: 32 random bytes (URL-safe). The browser keeps the token in an httpOnly cookie; the
  database keeps only its SHA-256 hash, so a leaked database does not leak live sessions.
* Rate limiting: in-process sliding windows. Fine for one local process; a multi-instance deployment
  would move this to Redis or the database.
* Log scrubbing: a logging.Filter that redacts PANs, session tokens, card/account-like digit runs and
  e-mail addresses from every log record before it is written.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque

# ---------------------------------------------------------------- passwords
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    _ph = PasswordHasher()  # argon2id, library defaults (m=64 MiB, t=3, p=4)
    PASSWORD_SCHEME = "argon2id"
except ImportError:  # pragma: no cover - exercised only where argon2-cffi is unavailable
    _ph = None
    PASSWORD_SCHEME = "bcrypt"

PASSWORD_MIN, PASSWORD_MAX = 10, 128
_COMMON = {"password12", "password123", "1234567890", "qwertyuiop", "letmein123", "iloveyou12", "finora1234",
           "welcome123", "admin12345", "passw0rd12", "0987654321", "abcdefghij", "1111111111", "password1234"}


def password_problem(password: str, email: str = "") -> str | None:
    if len(password) < PASSWORD_MIN:
        return f"Use at least {PASSWORD_MIN} characters."
    if len(password) > PASSWORD_MAX:
        return f"Use at most {PASSWORD_MAX} characters."
    if password.lower() in _COMMON or len(set(password)) < 4:
        return "That password is too easy to guess. Try a short phrase of a few words."
    local = email.split("@")[0].lower()
    if local and len(local) >= 4 and local in password.lower():
        return "Do not include your e-mail name in the password."
    return None


def hash_password(password: str) -> str:
    if _ph is not None:
        return _ph.hash(password)
    import bcrypt  # pragma: no cover

    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()  # pragma: no cover


def verify_password(stored: str, password: str) -> bool:
    try:
        if stored.startswith("$argon2"):
            if _ph is None:  # pragma: no cover
                return False
            return _ph.verify(stored, password)
        if stored.startswith("$2"):
            import bcrypt

            return bcrypt.checkpw(password.encode()[:72], stored.encode())
    except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
        return False
    return False


def needs_rehash(stored: str) -> bool:
    return _ph is not None and stored.startswith("$argon2") and _ph.check_needs_rehash(stored)


# A real hash of a random password: verifying against it when the e-mail is unknown keeps the response
# time of "unknown e-mail" and "wrong password" the same, so login cannot be used to discover accounts.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

# ---------------------------------------------------------------- tokens
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(str(a), str(b))


def ip_hash(ip: str | None, salt: str) -> str | None:
    if not ip:
        return None
    return hashlib.sha256((salt + ip).encode()).hexdigest()[:16]


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """Sliding-window counter: allow at most `limit` events per `window` seconds for each key."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: float, now: float) -> deque:
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        return q

    def hit(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Record one event. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, window, now)
            if len(q) >= limit:
                return False, max(1, int(q[0] + window - now) + 1)
            q.append(now)
            return True, 0

    def count(self, key: str, window: float) -> int:
        with self._lock:
            return len(self._prune(key, window, time.monotonic()))

    def blocked(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Is this key already at its limit (without recording a new event)?"""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, window, now)
            if len(q) >= limit:
                return True, max(1, int(q[0] + window - now) + 1)
            return False, 0

    def add(self, key: str):
        with self._lock:
            self._hits[key].append(time.monotonic())

    def clear(self, key: str | None = None):
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


limiter = RateLimiter()

# ---------------------------------------------------------------- log scrubbing
_SCRUB = [
    (re.compile(r"\b[A-Za-z]{5}[0-9]{4}[A-Za-z]\b"), "[PAN]"),                                  # PAN
    (re.compile(r"(finora_session|finora_csrf|token|csrf[_-]?token|password)(=|\"?:\s*\"?)[^\s;&,\"']+", re.I), r"\1\2[REDACTED]"),
    (re.compile(r"\b\d[\d -]{7,}\d\b"), "[NUMBER]"),                                           # card / account / phone-like runs
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
]


def scrub(text: str) -> str:
    for rx, repl in _SCRUB:
        text = rx.sub(repl, text)
    return text


class ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        clean = scrub(msg)
        if clean != msg:
            record.msg, record.args = clean, ()
        return True


def install_log_scrubbing():
    f = ScrubFilter()
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy"):
        lg = logging.getLogger(name)
        if not any(isinstance(x, ScrubFilter) for x in lg.filters):
            lg.addFilter(f)
        for h in lg.handlers:
            if not any(isinstance(x, ScrubFilter) for x in h.filters):
                h.addFilter(f)

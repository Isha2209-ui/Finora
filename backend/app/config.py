"""Central configuration, read from environment variables / .env file."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:  # optional .env support
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover
    pass

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'finora.db'}")
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", BASE_DIR / "artifacts"))
DATASETS_DIR = BASE_DIR / "datasets"
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", BASE_DIR / "reports"))
PAN_PEPPER = os.getenv("PAN_PEPPER", "finora-local-pepper-change-me")

# AI CFO / LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # ollama | none
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")  # only for Ollama cloud models (e.g. nemotron-3-super:cloud)
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))

# "Today" for the demo data. Fixed so that results are reproducible.
AS_OF_DATE = os.getenv("AS_OF_DATE", "2026-10-31")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# --- Accounts, sessions & security -------------------------------------------
FINORA_ENV = os.getenv("FINORA_ENV", "development").strip().lower()  # development | production
IS_PRODUCTION = FINORA_ENV == "production"
SESSION_COOKIE = "finora_session"
CSRF_COOKIE = "finora_csrf"
CSRF_HEADER = "X-CSRF-Token"
SESSION_TTL_HOURS = _int("SESSION_TTL_HOURS", 168)  # 7 days
COOKIE_SECURE = _bool("COOKIE_SECURE", IS_PRODUCTION)
SANDBOX_TTL_HOURS = _int("SANDBOX_TTL_HOURS", 24)
LOGIN_MAX_FAILURES = _int("LOGIN_MAX_FAILURES", 5)        # per email, per window
LOGIN_IP_MAX_ATTEMPTS = _int("LOGIN_IP_MAX_ATTEMPTS", 30)  # per IP, per window
LOGIN_WINDOW_SECONDS = _int("LOGIN_WINDOW_SECONDS", 900)
REGISTER_IP_MAX = _int("REGISTER_IP_MAX", 10)              # per IP, per hour
UPLOAD_MAX_BYTES = _int("UPLOAD_MAX_BYTES", 5_000_000)
UPLOAD_MAX_PER_HOUR = _int("UPLOAD_MAX_PER_HOUR", 30)
CHAT_MAX_PER_MINUTE = _int("CHAT_MAX_PER_MINUTE", 20)
ENABLE_RETRAIN_ENDPOINT = _bool("ENABLE_RETRAIN_ENDPOINT", not IS_PRODUCTION)
AUDIT_IP_SALT = os.getenv("AUDIT_IP_SALT", PAN_PEPPER)

_DEFAULT_PEPPERS = {"finora-local-pepper-change-me", "change-this-to-a-long-random-string"}
if IS_PRODUCTION:
    if PAN_PEPPER in _DEFAULT_PEPPERS or len(PAN_PEPPER) < 24:
        raise RuntimeError("FINORA_ENV=production requires PAN_PEPPER to be set to a long random secret.")
    if not COOKIE_SECURE:
        raise RuntimeError("FINORA_ENV=production requires COOKIE_SECURE=true (HTTPS only cookies).")

for d in (ARTIFACTS_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

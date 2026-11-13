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

for d in (ARTIFACTS_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

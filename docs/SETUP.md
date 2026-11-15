# Finora: local setup guide

Finora runs entirely on your own machine: a FastAPI backend with SQLite, a React frontend, the trained ML models shipped in the repository, and an optional local language model through Ollama. No cloud service is needed.

**Tested:** Phase 9, 2026-11-15, macOS (Apple Silicon), Python 3.14.0, Node 20.20.0.
- **Setup:** `./setup.sh` was run on a fresh copy containing exactly the files git ships (no database, no raw datasets). It finished in 2 min 38 s.
- **Tests:** 515 passed and 8 skipped (the skips are SCF raw-data checks, which skip by design when the raw file is absent).
- **Running app:** the API reported all five models loaded and the AI CFO available on `qwen2.5:3b`, and the frontend built.

## 1. Prerequisites

| Need | Version | Check | Notes |
|---|---|---|---|
| macOS or Linux shell | — | — | The scripts are bash. Windows: use WSL. |
| Python | **3.11+** (tested 3.14.0) | `python3 --version` | |
| Node.js + npm | **20+** (tested 20.20.0) | `node -v` | |
| Disk / RAM | about 1.5 GB (Python packages, node_modules, about 2 GB for the model) / 8 GB RAM | | The model needs about 2 GB of RAM while answering. |
| Ollama (optional) | current | `ollama --version` | Powers the AI CFO's wording. Without it the assistant runs in "calculator mode". |
| PostgreSQL (optional) | 14+ | `psql --version` | `setup.sh` uses it if a `finora` database can be created; otherwise SQLite. SQLite is the tested default. |

## 2. Install

```bash
git clone <your copy of the repository> finora
```

```bash
cd finora
```

```bash
./setup.sh
```

`setup.sh` does the following:
1. Creates `backend/venv` and installs `backend/requirements.txt`: FastAPI, SQLAlchemy, pandas, scikit-learn, XGBoost, SHAP, argon2-cffi, reportlab, pytest and others.
2. Writes `backend/.env` from `.env.example`. If PostgreSQL is not available it removes `DATABASE_URL`, so SQLite (`backend/finora.db`) is used.
3. Loads the demo data (`python -m app.data.seed`): four fictional template people and the synthetic population used by the demo.
4. Checks the shipped models (`python -m app.ml.train check`). It does **not** retrain: the trained artefacts are in `backend/artifacts/real/`, and `active.json` records which version is live and its SHA-256.
5. Runs the backend tests on a temporary copy of the database.
6. Runs `npm install` in `frontend/`.

## 3. Local AI model (Ollama + Qwen 2.5 3B)

1. Install Ollama from https://ollama.com/download (macOS app or `brew install ollama`).
2. Download the model once (about 1.9 GB):
   ```bash
   ollama pull qwen2.5:3b
   ```
3. Check that it runs:
   ```bash
   ollama run qwen2.5:3b "Say hello in five words"
   ```

The Ollama app keeps the server running on `http://localhost:11434`. Finora only talks to that local URL. Remote and cloud models are refused (`app/cfo/llm.py`).

## 4. Configuration (`backend/.env`)

| Setting | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | unset → SQLite `backend/finora.db` | Set to a PostgreSQL URL to use Postgres |
| `LLM_PROVIDER` | `ollama` | `none` switches the AI CFO to calculator mode |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `qwen2.5:3b` | Local model only |
| `PAN_PEPPER` | placeholder | Change it to a long random string |
| `REGISTER_IP_MAX` | `0` (no limit) | Sign-ups per IP per hour. Set e.g. `10` if the app is ever exposed beyond your machine. |
| `LOGIN_IP_MAX_ATTEMPTS` | 30 | **Failed** sign-ins per IP per 15 minutes. Successful sign-ins never count. |
| `LOGIN_MAX_FAILURES` | 5 | Failed sign-ins per e-mail per 15 minutes before a temporary lock |
| `SESSION_TTL_HOURS` / `SANDBOX_TTL_HOURS` | 168 / 24 | Session lifetime; demo-copy lifetime |
| `UPLOAD_MAX_BYTES` / `STATEMENT_MAX_ROWS` | 25,000,000 / 150,000 | Statement import limits |
| `FINORA_ENV` | `development` | `production` refuses default secrets and requires `COOKIE_SECURE=true` |

## 5. Run

```bash
./run.sh
```

Open **http://localhost:5173**. API docs (Swagger) are at http://127.0.0.1:8001/docs. Stop with Ctrl+C.

To run the parts separately, use two terminals:

```bash
cd backend && source venv/bin/activate && uvicorn app.main:app --port 8001
```

```bash
cd frontend && npm run dev
```

Health check: `curl -s localhost:8001/api/health`. It should show `"models": {… all true}` and `"ai_cfo": {"available": true, "model": "qwen2.5:3b", "local_only": true}`.

## 6. Tests

```bash
cd backend && source venv/bin/activate && pytest -q
```

The full suite passes 523 tests on the development machine (515 + 8 skipped on a fresh copy without raw datasets). Tests run on a temporary copy of the database and never touch `finora.db`.

**Browser suites:** these need the app running and the Playwright CLI.
```bash
npm install -g @playwright/cli@latest
```
```bash
cd frontend && playwright-cli open
```
```bash
playwright-cli --raw run-code --filename=e2e/p9_walkthrough.js
```
See [frontend/e2e/README.md](../frontend/e2e/README.md) for all eight scripts.

**Live AI CFO check:** this needs Ollama and the running app.
```bash
cd backend && venv/bin/python -m tests.live_cfo_check
```

## 7. Retraining the models (optional)

You do not need this to run Finora. Retraining needs the raw public datasets (git-ignored), downloaded with:
```bash
cd backend && venv/bin/python -m app.ml.data.acquire <dataset>
```
Then train, check and activate:
```bash
venv/bin/python -m app.ml.train <model> --approved
```
```bash
venv/bin/python -m app.ml.train check
```
```bash
venv/bin/python -m app.ml.train activate <model> <version> --reason "…"
```
Sources, licences and methods are in [ML_PROVENANCE.md](ML_PROVENANCE.md) and [PHASE_6_TRAINING.md](PHASE_6_TRAINING.md).

## 8. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `Another Finora server process is already using finora.db` at start-up | One backend process per database (a lock file is enforced) | Stop the other server (`pkill -f "uvicorn app.main:app"`). Do not use `--workers 2`. |
| `Address already in use` on 8001 or 5173 | A previous run is still alive | `lsof -iTCP:8001 -sTCP:LISTEN`, then stop that process |
| AI CFO says "calculator mode" / `available: false` | Ollama not running, or the model not pulled | Open the Ollama app; `ollama pull qwen2.5:3b`; check with `curl localhost:11434/api/tags` |
| First AI answer takes 20–60 s | The model is loading into memory | Warm it with `ollama run qwen2.5:3b "hi"`. Later answers take about 8–11 s on an 8 GB M2. |
| `'<model>' artifact is missing or does not match its recorded checksum` | An artefact file was changed or not copied | Restore `backend/artifacts/` from git (`git checkout -- backend/artifacts`) |
| `pip install` fails building a package | Python too old, or missing build tools | Use Python 3.11+. On macOS run `xcode-select --install`. |
| Sign-up says the e-mail exists | E-mails are unique per database | Sign in instead, or use another address |
| Statement upload refused: "Could not find a header row…" | The file is not a CSV statement with date, description and amount columns | Export CSV from your bank. PDF and Excel are not supported. |
| `npm run dev` fails on old Node | Vite 7 needs Node 20+ | Upgrade Node |
| Tests skip 8 peers checks | The SCF raw file is not downloaded | Expected. `python -m app.ml.data.acquire scf2022` enables them. |

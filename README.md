# Finora

**AI-powered personal financial intelligence, FIRE planning and an AI CFO.**

Enter a (demo) PAN and Finora loads that person's whole financial identity — every bank account, credit card,
stock, mutual fund, SIP, deposit, property, loan and insurance policy — then analyses it with trained ML models,
projects the path to financial independence, simulates big purchase decisions and answers questions through an
AI assistant that can only state numbers the backend has computed.

> All demo data is **synthetic**. A real PAN does not give access to anyone's finances; a production system would
> use the RBI Account Aggregator framework with user consent. Finora gives educational guidance, not licensed
> financial advice.

## Run it (macOS)

```bash
./setup.sh      # first time only: Python env, packages, database, demo data, tests
./run.sh        # starts backend + frontend
```

Open **http://localhost:5173**, create a local account (e-mail + password) and sign in. In VS Code: `Cmd+Shift+B` runs the same thing ("Run Finora").

Demo PANs: `ABCDE1234F` (balanced saver) · `PQRST5678K` (overspender, 3 cards) · `LMNOP2345D` (loan-heavy) · `XYZAB9876C` (freelancer)

| Needs | Notes |
|---|---|
| Python 3.11+ and Node 20+ | required |
| PostgreSQL (Postgres.app) | optional — `setup.sh` uses it if present, otherwise SQLite |
| Ollama + `ollama pull qwen3.5:4b` | optional — powers the AI CFO's wording; without it the assistant answers in "calculator mode" |

Useful commands (inside `backend/` with the venv active):

```bash
pytest -q                    # 206 tests
python -m app.ml.train       # retrain all models, rewrite artifacts/metrics.json
python -m app.data.seed      # reset the database to the original demo data
```

API documentation (Swagger): http://127.0.0.1:8001/docs

## What is inside

```
backend/app/
  models.py            22 tables (SQLAlchemy)
  data/                synthetic generator, bank-statement narrations, seed script
  services/            cleaning, calculations, FIRE, decision simulator, tax, recommendations, reports, CSV import
  ml/                  credit_risk, categoriser, anomaly, forecast, peers, train.py
  cfo/                 router -> tools -> language model -> number guard -> rule-based fallback
  routes/              REST API
backend/datasets/      UCI "Default of Credit Card Clients" (30,000 real accounts)
backend/artifacts/     trained models (.joblib) + metrics.json
backend/tests/         formulas, cleaning, models, API, AI CFO
frontend/src/pages/    15 modules (React + Vite + Tailwind + Recharts)
```

## The models (all measured on held-out data, each against a simple baseline)

| Model | Data | Result | Baseline |
|---|---|---|---|
| Credit risk — XGBoost + SHAP | 30,000 real card accounts (UCI) | ROC-AUC 0.786 (5-fold CV 0.779) | Logistic regression 0.761 |
| Transaction categoriser — TF-IDF + logistic regression | 9,436 labelled narrations, 15 statement formats | Macro-F1 0.997 on 3 formats never seen | Keyword rules 0.41 |
| Anomaly detector — Isolation Forest | 230k transactions, tested on 48 held-out users | F1 0.57 on planted cases | "Over 3× usual" rule 0.41 |
| Cash-flow forecaster — XGBoost | 3,600 user-months, chronological split | MAE ₹8,517 (9.6%) | 3-month average ₹9,294 (10.6%) |
| Peer groups — K-Means | 240 users, 8 behaviour features | k = 3, silhouette 0.35 | — |

Exact, current figures are in `backend/artifacts/metrics.json` and on the **Model Lab** page.

**Known limits (state these, don't hide them)**

- Transaction, forecast and peer models are trained on synthetic data; the anomaly score is not a fraud probability.
- The credit-risk data is from Taiwan (2005): it captures behaviour patterns, not Indian bureau scores. Demographic columns were dropped on purpose.
- The categoriser gets only ~15% right on brand names it has never seen; those are returned with low confidence for review.
- Market prices are stored "as of" values, not a live feed. Tax follows FY 2026-27 slabs without surcharge.

## Accounts, ownership and security

- **Accounts:** e-mail + password, hashed with argon2id (`argon2-cffi`; bcrypt is accepted as a fallback). No verification e-mail in this local version.
- **Sessions:** random 256-bit token in an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production); the database stores only its SHA-256 hash. Sign-out revokes the session server-side.
- **CSRF:** every state-changing request must echo the session's CSRF token in `X-CSRF-Token`.
- **Ownership:** every profile route checks the signed-in account against the profile's `kind`. Demo *templates* are readable by any account and never writable. *Private* and *sandbox* profiles are visible only to their owner (others get 404). The 240 synthetic *population* profiles are used only for model training and cannot be reached through the API.
- **Training data:** models train only on the synthetic population and the public UCI dataset, never on account holders' profiles (there is a test for this).
- **Limits & audit:** rate limits on sign-in (per account and per IP), sign-up, uploads and chat; uploads are capped at 5 MB. Sign-ins, profile creation and deletion, uploads, exports, reports and retraining are written to `audit_events`, which holds IDs and counts only.
- **Logs:** a logging filter redacts PAN-like strings, long card or account numbers, e-mail addresses and session tokens.
- **Config:** secrets come from the environment (`.env`, git-ignored). With `FINORA_ENV=production` the server refuses to start on a default `PAN_PEPPER` or without `COOKIE_SECURE=true`.

## How the AI CFO avoids making numbers up

1. **Route** — rules recognise the question and pick a calculator/model (the language model's tool-calling is used only for open-ended questions).
2. **Compute** — the backend runs it on the person's data.
3. **Explain** — a local model (Qwen via Ollama; NVIDIA Nemotron via `OLLAMA_MODEL`) words the answer.
4. **Verify** — every number in that text is checked against the computed result; any mismatch discards the text and a rule-written answer is shown.

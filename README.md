# Finora

**AI-powered personal financial intelligence, Machine learning models , FIRE planning and an AI CFO.**

Enter a (demo) PAN and Finora loads that person's whole financial identity — every bank account, credit card,
stock, mutual fund, SIP, deposit, property, loan and insurance policy — then analyses it with trained ML models,
projects the path to financial independence, simulates big purchase decisions and answers questions through an
AI assistant that can only state numbers the backend has computed.

> All demo data is **synthetic**. A real PAN does not give access to anyone's finances; a production system would
> use the RBI Account Aggregator framework with user consent.

**Documentation:** [setup guide](docs/SETUP.md) · [project status](docs/PROJECT_STATUS.md) · [verification](docs/PHASE_9_VERIFICATION.md) ·
[ML provenance](docs/ML_PROVENANCE.md) · [demo script](docs/DEMO_SCRIPT.md) · [viva Q&A](docs/VIVA_QA.md) · [screenshots](docs/SCREENSHOTS.md)

## Run it (macOS)

```bash
./setup.sh      # first time only: Python env, packages, database, demo data, tests
./run.sh        # starts backend + frontend
```

**One server process per database.** The backend locks `backend/finora.db.lock` at start-up; a second backend (or `uvicorn --workers 2`) on the same database refuses to start. Run tests freely while it runs: they use a temporary copy of the database.

Open **http://localhost:5173**, create a local account (e-mail + password) and sign in. In VS Code: `Cmd+Shift+B` runs the same thing ("Run Finora").

After signing in you choose **Explore demo identity** or **Build my financial identity**.

- **Demo identities** are four fictional people with synthetic data (demo identifiers `ABCDE1234F` balanced saver · `PQRST5678K` overspender with 3 cards · `LMNOP2345D` loan-heavy · `XYZAB9876C` freelancer). Opening one gives you a private **sandbox** copy: edit anything, press **Reset demo** to restore it, and it is deleted after 24 hours. The four originals are read-only templates and never change.
- **Your own profile** is private to your account. No bank, bureau or government system is ever contacted: a real PAN finds nothing.

| Needs | Notes |
|---|---|
| Python 3.11+ and Node 20+ | required |
| PostgreSQL (Postgres.app) | optional — `setup.sh` uses it if present, otherwise SQLite |
| Ollama + `ollama pull qwen2.5:3b` | optional — the local AI CFO (Qwen 2.5 3B); without it the assistant answers in "calculator mode" |

Useful commands (inside `backend/` with the venv active):

```bash
pytest -q                    # 523 tests
python -m app.ml.train check # acceptance checks of the shipped models (retraining needs the raw datasets: docs/SETUP.md §7)
python -m app.data.seed      # rebuild demo data (refuses if accounts exist; --force deletes them too)
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
backend/datasets/      raw public datasets for retraining (git-ignored; not needed to run)
backend/artifacts/     trained models: real/<model>/<version>/ (model.joblib, metrics.json, provenance.json) + active.json
backend/tests/         formulas, cleaning, models, API, AI CFO
frontend/src/pages/    7 areas + Settings (React 19 + Vite 7 + Tailwind v4 + Recharts)
frontend/e2e/          Playwright CLI browser suites
```

## The models (trained on real public data; full details in [docs/ML_PROVENANCE.md](docs/ML_PROVENANCE.md))

| Capability | Algorithm | Data | Measured result |
|---|---|---|---|
| Credit Risk | XGBoost + SHAP | UCI Default of Credit Card Clients, 30,000 accounts (Taiwan 2005) | Test ROC-AUC 0.783 (logistic regression 0.760) |
| Peer Benchmarking | Weighted K-Means (k = 3) | Federal Reserve SCF 2022, 4,595 US families | Silhouette 0.219; cross-implicate ARI ≥ 0.867 |
| Transaction Categoriser | TF-IDF + logistic regression | Oklahoma / DC purchase cards; MoneyVis (UK) | Macro-F1 0.600 held-out merchants (keyword rules 0.149) |
| Anomaly Detection Scanner | Isolation Forest | Oklahoma purchase cards, 1.05 M transactions | Flag stability ≥ 0.82; accuracy not measured (human review pending) |
| Cash-Flow Forecast | XGBoost | MoneyVis, one UK person, 2015–2022 | MAE 856.93 vs 3-month average 809.49 (does not beat it; shown beside it) |
| Model Lab | registry, checksums, metrics | — | — |

**Known limits (state these, don't hide them)**

- Credit risk is a Taiwan 2005 pattern, not an Indian bureau score. Demographic columns were dropped on purpose.
- The categoriser is unmeasured on Indian UPI/NEFT narrations; suggestions under 0.5 confidence go to Review.
- The anomaly score means "unusual for you", not fraud. Peers are US households.
- Market prices are stored "as of" values, not a live feed. Tax follows FY 2026-27 slabs without surcharge.

## Accounts, ownership and security

- **Accounts:** e-mail + password, hashed with argon2id (`argon2-cffi`; bcrypt is accepted as a fallback). No verification e-mail in this local version.
- **Sessions:** random 256-bit token in an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production); the database stores only its SHA-256 hash. Sign-out revokes the session server-side.
- **CSRF:** every state-changing request must echo the session's CSRF token in `X-CSRF-Token`.
- **Ownership:** every profile route checks the signed-in account against the profile's `kind`. Demo *templates* are readable by any account and never writable. *Private* and *sandbox* profiles are visible only to their owner (others get 404). Synthetic *population* profiles cannot be reached through the API (tested).
- **Training data:** models train only on public datasets, never on account holders' profiles (there is a test for this).
- **Limits & audit:** rate limits on sign-in (per account and per IP), sign-up, uploads and chat; uploads are capped at 25 MB and 150,000 rows. Sign-up is not rate-limited by default (`REGISTER_IP_MAX=0`); set it for any public deployment. Sign-ins, profile creation and deletion, uploads, exports, reports and retraining are written to `audit_events`, which holds IDs and counts only.
- **Logs:** a logging filter redacts PAN-like strings, long card or account numbers, e-mail addresses and session tokens.
- **Config:** secrets come from the environment (`.env`, git-ignored). With `FINORA_ENV=production` the server refuses to start on a default `PAN_PEPPER` or without `COOKIE_SECURE=true`.

## How the AI CFO avoids making numbers up

1. **Guards** — requests to change data, to look at another profile or to pick stocks/funds get fixed replies; no model call.
2. **Plan** — the local model (Qwen 2.5 3B via Ollama; cloud models are refused) writes a JSON plan of read-only operations.
3. **Compute** — read-only tools run them on the signed-in profile only.
4. **Write and verify** — the model drafts the answer; every number is checked against the computed results, and unsupported claims are rejected. A failed draft is rewritten once, otherwise a rule-written answer is shown.

Details and evaluation: [docs/PHASE_7_VERIFICATION.md](docs/PHASE_7_VERIFICATION.md), [docs/PHASE_9_VERIFICATION.md](docs/PHASE_9_VERIFICATION.md).

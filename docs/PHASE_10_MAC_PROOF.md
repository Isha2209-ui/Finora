# Phase 10: Mac proof

Executed on the owner's machine, 2026-11-15, starting from `master` at `ff71507` (Phase 9).

## Machine

| | |
|---|---|
| Hardware | MacBook Air, `Mac14,2`, Apple M2, **8 GB** RAM, arm64 |
| macOS | 27.2.1 (build 26B131) |
| Disk | 228 GB total, 23 GB free |
| Python | 3.14.0 (existing `backend/venv`, dependencies already installed) |
| Node / npm | 20.20.0 / 10.8.2 (existing `frontend/node_modules`) |
| Ollama | 0.40.16; `qwen2.5:3b` already downloaded (1.9 GB); runs 100% on the GPU, about 2.3 GB loaded, 8,192-token context |

Nothing was reinstalled or downloaded.

## Results

| Check | Result |
|---|---|
| Database | SQLite `backend/finora.db` (360 MB, no `DATABASE_URL`), schema migrated at start-up, connected. Backed up first to `backend/backups/finora-before-phase10-20261115-205423.db`. Nothing reset or deleted. |
| Cold start with `./run.sh` | Backend healthy in **4 s**; frontend serving in **4 s** |
| Restart with `./run.sh` | Both up in **3 s** |
| Authentication | Unauthenticated `/api/auth/me` → 401; registration, sign-in, sign-out and protected routes pass in the walkthrough |
| ML models | All 5 shipped artefacts present, versions recognised, every SHA-256 matches `active.json`, all loaded (`/api/health`): credit_risk `v20261114-211415`, categoriser `v20261114-222418`, anomaly `v20261114-222608`, forecast `v20261114-215913`, peers `v20261114-215812`. Invoked in the walkthrough (credit risk, peers, categoriser, anomaly, forecast). |
| Ollama / Qwen | Backend detects `qwen2.5:3b`; `ai_cfo.available = true`, `local_only = true`. No cloud model. |
| Main workflows (real browser, Chromium, against the `run.sh` instance) | **25/25** (`frontend/e2e/p9_walkthrough.js`): registration and login, onboarding, Home, Plan, Goals, Money, Accounts, Transactions, Spending, Investments, Debts, Cash flow, Retirement, What-if, all six ML screens, Model Lab, AI CFO, Import, Review, Records, Reports (PDF), Profile & privacy, Settings, sign-out, second-account isolation. On-screen figures equal the API. 0 console errors, 0 server errors. |
| AI CFO after restart (live, `tests/live_cfo_check.py`) | **16/16**: real balances, net worth, period spending, follow-up context, read-only refusal, no false modification claim, cross-profile refusal, injection resisted, no stock/fund picks, empty profile honest, data unchanged ([PHASE_10_CFO_LIVE_CHECK.json](PHASE_10_CFO_LIVE_CHECK.json)) |
| AI CFO response time | Model-written answers: median **4.6 s**, max **8.0 s** (model warm). In the browser walkthrough, run while other apps were heavily swapping: 13 s. Guarded replies (change requests, other profiles, stock picks): about 0.1 s. |
| Persistence | A fictional account ("Mac Proof Demo (fictional)" profile, "Phase 10 persistence goal" ₹1,23,456 by 2028-06-30) was created and re-read after a fresh sign-in, and **still present after stopping and restarting** `./run.sh`. |
| Finora memory | Backend 70–130 MB; Vite 45–75 MB; Qwen runner about 2.3 GB (GPU). |

## Memory on 8 GB: the one presentation risk

During the test the machine was using **5.2 GB of 6 GB swap**, with 19% of memory free. Finora itself is small; the pressure came from other open apps (ChatGPT, Chrome, Outlook, the Claude app and the test browsers, which are now closed). Swapping makes the first AI answer slower.

**Before presenting:** quit ChatGPT, Outlook and unneeded Chrome windows, then warm the model.

## Presentation runbook

1. Quit apps you don't need (see above).
2. Open the Ollama app (menu-bar icon), then warm the model:
   ```bash
   ollama run qwen2.5:3b "hi"
   ```
3. Start Finora (keep this Terminal window open; Ctrl+C stops it):
   ```bash
   cd ~/Developer/finora && ./run.sh
   ```
4. Open **http://localhost:5173**.
5. Create an account (any e-mail and a 10+ character password) or sign in, then choose the demo person **Aarav Mehta** (fictional, labelled "demo copy").
6. Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
7. **Health check if anything looks wrong:**
   ```bash
   curl -s localhost:8001/api/health
   ```
   All five models should be `true` and `ai_cfo.available` should be `true`.
8. **Repeatable:** stopping and re-running `./run.sh` brings everything back in about 3 s. A demo copy can be reset from its banner ("Reset demo").

## Not covered
- Safari and Firefox were not tested; the browser checks used Chromium.
- The persistence check re-read the record through the API after re-signing in and after a restart; a browser refresh of persisted data is covered by the Phase 8 workflow suite (43/43).

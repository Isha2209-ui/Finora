# Phase 8 route-by-route checklist

Every route that existed before Phase 8, its redesigned home, and how it was verified. "Smoke" means the Playwright smoke run (`p8_smoke.js`) opened it, found exactly one `h1`, a selected tab, non-empty content, no crash and no console error. "Redirect" means the old URL was opened and the final URL compared exactly. Workflows are listed in [PHASE_8_VERIFICATION.md](PHASE_8_VERIFICATION.md).

| Old route (before Phase 8) | Old page | New home | Old URL behaviour | Verified |
|---|---|---|---|---|
| `/` (signed out) | Sign in / register | Sign in / register (redesigned) | same | smoke: validation, invalid credentials, register |
| `/` (no profile) | Lookup (start) | Start (redesigned, same route) | same | smoke + responsive: demo path, private path |
| `/` → `/plan` | Finora Plan | **Home** `/` (new) + Plan area | `/` is Home now | smoke |
| `/plan` | Finora Plan (3 steps) | Plan → Priorities / Actions / Your plan | same route, tabs | smoke (all 6 Plan tabs) |
| `/identity` | Financial Identity | Money → Overview, plus Plan → Health | redirect → `/money?tab=overview` | redirect + smoke |
| `/records` | My Data | Data → Records (Goals also at Plan → Goals) | redirect → `/data?tab=records` | redirect + add/delete goal workflow |
| `/statements` | Import Statements | Data → Import | redirect → `/data?tab=import` | redirect + import workflow |
| `/accounts` | Accounts & Cards | Money → Accounts & cards | redirect → `/money?tab=accounts` | redirect + smoke |
| `/investments` | Investments & Assets | Money → Investments | redirect → `/money?tab=investments` | redirect + smoke |
| `/insights` | Statement Intelligence | Money → Spending (8 views) | redirect → `/money?tab=spending` | redirect + spending workflow |
| `/review` (incl. `?import=`) | Review & Corrections | Data → Review | redirect keeps the query: `/data?tab=review&import=…` | redirect (with query) + smoke |
| `/transactions` | Transaction Intelligence | Money → Transactions | redirect → `/money?tab=transactions` | redirect + search/sort/page/drawer workflow |
| `/scanner` | Anomaly Scanner | Risk & Models → Unusual activity | redirect → `/models?tab=unusual` | redirect + smoke |
| `/forecast` | Cash-Flow Forecast | Future → Cash flow | redirect → `/future?tab=cash-flow` | redirect + smoke |
| `/credit` | Credit & Debt | Risk & Models → Credit risk, plus Money → Debts | redirect → `/models?tab=credit-risk` | redirect + scoring + payoff workflows |
| `/peers` | Peer Benchmarking | Risk & Models → Peers | redirect → `/models?tab=peers` | redirect + smoke |
| `/budget` | Budget, Savings & Tax | Money → Spending → Budget, Future → Savings, Plan → Tax | redirect → `/money?tab=spending&view=budget` | redirect + tax workflow |
| `/fire` | FIRE & Retirement | Future → Retirement | redirect → `/future?tab=retirement` | redirect + input workflow |
| `/decision` | Decision Simulator | Future → What if | redirect → `/future?tab=what-if` | redirect + simulate workflow |
| `/cfo` | AI CFO | Ask `/ask` (+ panel on every page) | redirect → `/ask` | redirect + Ask workflow |
| `/recommendations` | Recommendations | Plan → Actions (below the ranked steps) | redirect → `/plan?tab=actions` | redirect + accept/reopen workflow |
| `/reports` | Reports | Data → Reports & export | redirect → `/data?tab=reports` | redirect + smoke |
| `/models` | Model Lab | Risk & Models (Overview, Model Lab tab) | same route, now an area | smoke + `?model=` deep link |
| `/models/review` | Anomaly blinded review | same route (linked from Model Lab and Unusual activity) | same | smoke |
| `/data` | Profile & Data | Data area (Profile & privacy tab); Settings → Profiles | same route, now an area | smoke |
| (new) `/money` `/future` `/ask` `/settings` | — | new areas | — | smoke (every tab) |
| unknown route | → `/plan` | → `/` (Home) | — | — |

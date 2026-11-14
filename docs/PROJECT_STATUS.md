# Finora: project status

The roadmap is the original 11-phase plan agreed on 14 Nov 2026. Phases are built in order, verified, and merged into `master` only with the product owner's approval.

| # | Phase | Status | Verification |
|---|---|---|---|
| 1 | Accounts and security | Merged | [PHASE_1-3_VERIFICATION.md](PHASE_1-3_VERIFICATION.md) |
| 2 | Demo vs private profiles | Merged | [PHASE_1-3_VERIFICATION.md](PHASE_1-3_VERIFICATION.md) |
| 3 | Manual entry for everything | Merged | [PHASE_1-3_VERIFICATION.md](PHASE_1-3_VERIFICATION.md) |
| 4 | Statement import, rebuilt | Merged (two independent audits, release-blocker round, closure checks) | [PHASE_4_VERIFICATION.md](PHASE_4_VERIFICATION.md) |
| 5 | Finora Plan, the main page | Merged | [PHASE_5_VERIFICATION.md](PHASE_5_VERIFICATION.md) |
| 6 | Models and provenance (train every model locally, record provenance) | Not started | - |
| 7 | Local AI CFO with Qwen | Not started | - |
| 8 | Product shell and UI (product-wide guided experience) | Not started | - |
| 9 | Verification and documentation | Not started | - |
| 10 | Mac proof | Not started | - |
| 11 | Deployment (last) | Not started | - |

## Carried-forward limitations
- **Phase 4:**
  - CSV only.
  - Real-bank classification accuracy is unmeasured (the categoriser is trained on synthetic narrations).
  - Look-alike rows on the same account are counted until reviewed.
  - A crashed import is rolled back after up to 2 minutes.
  - About 13–16 s of analysis after a 150k-row import.
  - One server process per database (enforced by a lock).
- **Phase 5:**
  - The projected health score does not re-project the debt and credit-use components.
  - FIRE does not reinvest freed EMIs after debt repayment.
  - Each action's effect is measured on its own.
  - The ranking weights are a published heuristic.
- **Phase 8:** a responsive app shell, including the mobile sidebar.

## Working rules
- **Database:** tests run on a temporary copy of the development database and never touch it. The development database is never reset or replaced, and a backup is taken before each phase (`backend/backups/`).
- **Truthfulness:**
  - Synthetic data is never called real.
  - The anomaly model is not fraud detection.
  - The credit model is a Taiwan 2005 benchmark.
  - A PAN never fetches data.

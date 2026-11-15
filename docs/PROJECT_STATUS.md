# Finora: project status

The roadmap is the original 11-phase plan agreed on 14 Nov 2026. Phases are built in order, verified, and merged into `master` only with the product owner's approval.

| # | Phase | Status | Verification |
|---|---|---|---|
| 1 | Accounts and security | Merged | [PHASE_1-3_VERIFICATION.md](PHASE_1-3_VERIFICATION.md) |
| 2 | Demo vs private profiles | Merged | [PHASE_1-3_VERIFICATION.md](PHASE_1-3_VERIFICATION.md) |
| 3 | Manual entry for everything | Merged | [PHASE_1-3_VERIFICATION.md](PHASE_1-3_VERIFICATION.md) |
| 4 | Statement import, rebuilt | Merged (two independent audits, release-blocker round, closure checks) | [PHASE_4_VERIFICATION.md](PHASE_4_VERIFICATION.md) |
| 5 | Finora Plan, the main page | Merged | [PHASE_5_VERIFICATION.md](PHASE_5_VERIFICATION.md) |
| 6 | Models and provenance (train every model locally, record provenance) | Merged (owner-authorised, 2026-11-15) | [PHASE_6_VERIFICATION.md](PHASE_6_VERIFICATION.md), [PHASE_6_TRAINING.md](PHASE_6_TRAINING.md) |
| 7 | Local AI CFO with Qwen | Merged (owner-authorised, 2026-11-15); complete with documented limitations | [PHASE_7_VERIFICATION.md](PHASE_7_VERIFICATION.md) |
| 8 | Product shell and UI redesign (Apple-inspired refinement + Stripe-inspired usability) | Merged locally (owner-authorised, 2026-11-15): commit `b73e9e4` on `phase-8-ui-redesign` (kept), merge `a0fae1d` on `master`. Re-verified on `master`: backend 487, browser 5/60/43/55/12, build OK | [PHASE_8_VERIFICATION.md](PHASE_8_VERIFICATION.md) |
| 9 | Verification and evidence | Complete (2026-11-15); changes uncommitted on `master`, awaiting owner review. Backend 523/523; browser suites 5/5, 60/60, 43/43, 55/55, 12/12, walkthrough 25/25, debt edge 4/4; live AI CFO 16/16; fresh-copy setup passes. 9 defects found and fixed, each with a regression test | [PHASE_9_VERIFICATION.md](PHASE_9_VERIFICATION.md), [SETUP.md](SETUP.md), [ML_PROVENANCE.md](ML_PROVENANCE.md), [DEMO_SCRIPT.md](DEMO_SCRIPT.md), [VIVA_QA.md](VIVA_QA.md), [SCREENSHOTS.md](SCREENSHOTS.md) |
| 10 | Verification on the owner's MacBook Air M2 | Complete (2026-11-15) on the owner's MacBook Air M2 (8 GB): `./run.sh` up in 3–4 s; 5/5 models loaded and checksum-verified; qwen2.5:3b local AI CFO 16/16 live (median 4.6 s); browser walkthrough 25/25; persistence across restart confirmed. Risk: memory pressure from other apps (close them before presenting) | [PHASE_10_MAC_PROOF.md](PHASE_10_MAC_PROOF.md) |
| 11 | Public GitHub release and local installation (no cloud hosting) | Not started (waits for owner instruction) | - |

## Carried-forward limitations
- **Phase 6:**
  - The forecast (MoneyVis, one UK person) does not meet its acceptance criterion: it is less accurate than a 3-month average in testing, so it is always shown beside that average. Waiting on multi-person data; Berka needs permission.
  - The Anomaly Detection Scanner is not human-validated until the blinded review (300 items, two or more reviewers) is completed.
  - The categoriser is suggestion-only: it is not validated on Indian narrations.
  - Peer groups are US households.
  - Credit risk is a Taiwan 2005 benchmark.
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
- **Phase 8:**
  - Password change, preferences and password recovery have no backend endpoints and are listed as unavailable in Settings.
  - Charts inside AI answers were not built (the stream does not carry tool results).
  - The sign-up rate limit is off by default (`REGISTER_IP_MAX=0`); a public deployment should set it.
- **Phase 9:**
  - Not executed: a real screen reader, Safari and Firefox, and tablet/mobile screenshots of the Phase 9 fixes.
  - The record form accepts a loan whose EMI never clears it; this is now reported as "never paid off", not refused.
  - 3B-model wording can still vary; deterministic checks catch wrong numbers and unsupported claims, not every awkward phrase.

## Working rules
- **Database:** tests run on a temporary copy of the development database and never touch it. The development database is never reset or replaced, and a backup is taken before each phase (`backend/backups/`).
- **Truthfulness:**
  - Synthetic data is never called real.
  - The anomaly model is not fraud detection.
  - The credit model is a Taiwan 2005 benchmark.
  - A PAN never fetches data.

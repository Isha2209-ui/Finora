# Finora: verification log, Phases 1–3

Recorded 14 Nov 2026 on the development Mac (macOS, Python 3.14, Node 20, SQLite). Each entry gives what was checked,
how it was checked, and the result, including what failed first.

## Before merging Phases 1–2 into `master`

| Check | How | Result |
|---|---|---|
| Database backup is restorable | Copied `backups/finora-before-phase1.db` to a scratch folder, ran `PRAGMA integrity_check`, ran the migration on the copy, then ran a full analysis of `FINORA_USER_001` on the copy | `ok`. The copy has 244 profiles and 327,196 transactions, the same as live. The migration added 6 columns. The analysis ran with no model errors (net worth ₹29.77 L, health 95.2). The live database was not touched. |
| Security tests | `test_auth.py`, `test_sandbox.py` | 74/74 passed |
| Every profile-changing endpoint respects ownership | New `test_route_security.py` walks every registered route and checks its dependency tree | **First run passed vacuously.** FastAPI 0.162 wraps included routers, so a flat walk saw 0 API routes. Fixed: the walker now recurses, and a minimum route count makes a vacuous pass impossible. Now 4/4: 23 mutating routes, each either requiring write access (owner of a sandbox or private profile; templates answer 403) or listed with a reason (what-if calculators, the caller's own chat). |
| Merge | `git merge --ff-only phase-2-sandbox` | Fast-forward. Every commit kept; the database was not reset or recreated. |

A fresh backup was taken before Phase 3: `backups/finora-before-phase3.db`.

## Phase 3: manual financial identity

### Design decisions
- **No new data structures.** Manual entry (`app/records.py`, `/api/profiles/{id}/records/{type}`) writes to the
  existing tables, so manual data goes through the same loader, snapshot, models and recommendations pipeline as the demos.
- **Nothing invented.** A new profile holds personal details only. The previous "six months of your stated income" records were removed.
- **Unknown is never zero.** `coverage()` reports whether income and spending are known. Results that need missing data are
  `None` with a reason. Examples: a 100% savings rate when only income is known, runway with no expenses, FIRE planned on ₹1/yr.
- **Health score.** Pillars without data are left out and listed. The score is withheld unless at least one pillar is
  measured from real cash-flow data, so an empty profile does not score 66.7 just because it has no loans or cards on record.
- **Recurring payments now count.** They were stored but never used. They now feed "known fixed commitments"
  (recurring + EMIs + SIPs + premiums), which is reported separately and never used as measured spending.
- **Deletes don't silently destroy linked data.** Deleting an account or card that has transactions returns 409 unless
  `cascade=true`. Deleting a property only unlinks its loan.
- **Audit and ownership.** Every write records an audit row with the record type, its id and the names of the changed fields; values are never stored. Every write also invalidates the analysis cache.

### Tests (all in `backend/tests/`)
| File | What it proves |
|---|---|
| `test_demo_regression.py` | The four demo analyses match `golden/demo_analysis_before_phase3.json` value for value (1,198–1,674 values each). Only two explanatory texts were reworded. |
| `test_records.py` | For all 14 record types: create, list, patch and delete; validation, including cross-field rules on PATCH; unknown fields rejected; ownership and template isolation; same-profile references; cascade rules; audit records without values; ML categorisation. It also traces each entry into the results with exact arithmetic: net worth, liabilities, EMI ratio, savings rate, runway, FIRE inputs and corpus, retirement age, health pillars, recommendations appearing and disappearing, goals, commitments, anomaly and forecast models, export, chat, Decision Simulator and the FIRE what-if. Sandboxes have the same features. |
| `test_partial_profiles.py` | Nine partial profiles (empty → full) × every read endpoint, every planner and one question per AI CFO tool. No crashes, and no `None`, `NaN` or "₹0 for unknown" text. Missing data is never counted as zero. |

**Totals:** 271 backend tests passed with pytest exit code 0, and the frontend build passes.

### Failures found during Phase 3, and fixes
1. **The analysis crashed on 5 of 9 partial profiles.** An empty cash-flow window broke the analysis, and a card without statements broke the credit analysis. Fixed by the coverage-aware engine.
2. **Recommendation rules treated missing data as zero.** For example, "Emergency fund covers only 0.0 months" appeared with no expense data. Each rule now needs its inputs to be known.
3. **The AI CFO said "You earn about ₹0"** because its money formatter turned an unknown value into ₹0. It now says "not known yet", and each answer explains what is missing.
4. **Every PDF page footer said "synthetic demonstration data"**, private profiles included. Fixed.
5. **Four pages crashed in the browser on a bank-only profile** (Identity, Transactions, Budget, FIRE). **The FIRE card showed "75+" when the projection wasn't available.** Fixed. FIRE now asks for yearly expenses and labels the result "entered by you". An error boundary now contains any page failure.
6. **One of my test assumptions was wrong.** A first-ever Shopping purchase cannot be "×N your typical Shopping spend", so its anomaly severity is low, as designed. The test now gives the profile a normal shopping history.
7. **iCloud Drive incident.** The project lives on an iCloud-synced Desktop. Files were duplicated as `name 2.py` and two were renamed: `.env.example` became `.env 2`, and `Lookup.jsx` became `Lookup`. One Phase 3 commit picked up 11 of these copies, and the full suite reported 6 failed and 29 errors from stale duplicate tests. My command piped pytest into `tail`, which hid the failing exit code, so the commit went ahead. Checks showed `.env 2` was the example file, so no secret was committed. Fixed: renamed files restored, duplicates moved to `backend/backups/icloud-duplicates-2026-11-14/` (not deleted), the local unpushed commit amended, and `* 2` / `* 2.*` added to `.gitignore`. Exit codes are now checked directly.

### Browser walkthrough (built-in browser, local dev servers)
- Built a profile with **Build my financial identity**. It opened on **My Data** at 10% completeness, with every missing item explained.
- Added a bank account with the form. The impact panel showed *Net worth ₹0 → ₹3.00 L, completeness 10% → 20%*.
- Swept all 15 module pages twice: bank-only, then 3 months of income and transactions plus a card, loan, stock, SIP, PPF, health cover and goal. Each pass looked for crashes and for `NaN`, `null`, `undefined`, `None` and "75+". Both final sweeps were clean.
- Checked the numbers by hand: net worth ₹2.22 L, surplus ₹55,000, savings 50.0%, runway 5.45 months (₹3,00,000 / ₹55,000).
- Edited the TCS price ₹4,100 → ₹4,600 in the UI. The impact panel showed *Net worth ₹2.22 L → ₹2.32 L*, exactly 20 × ₹500.

All test accounts created during verification were deleted afterwards.

# Phase 6 verification (2026-11-15)

Branch `phase-6-models`. **Not committed, not merged.** Phase 7 has not started. Training details are in
`PHASE_6_TRAINING.md`; data sources are in `PHASE_6_DATA_ACQUISITION.md`.

## 1. Final model status (updated 2026-11-15 after the owner's "every built feature must be visible" instruction)

Two activation statuses exist (`app/ml/provenance.activate`):

- **accepted**: the predefined acceptance criteria were met;
- **experimental** (`--experimental`): the model is real-data, owner-approved and checksum-verified, but its criteria are unmet.
  - The unmet criteria and a reason are recorded in `active.json`.
  - Every output carries `model_info.status = experimental`.
  - Recommendations built on it say so.

| Model | Version | Status | User-facing access | Disclosure |
|---|---|---|---|---|
| Credit Risk Analysis (UCI Taiwan 2005) | v20261114-211415 | **Available (accepted)** | Credit & Debt: per-card score + SHAP; **"Score a card history"** form runs the model on entered inputs | Test ROC-AUC 0.783 vs LR 0.760; Taiwan 2005; not a bureau score; not validated for Indian borrowers |
| Peer Benchmarking (SCF 2022) | v20261114-215812 | **Available (accepted)** | New **Peer Benchmarking** page | US households, gross vs take-home income, card balance definition |
| Transaction Categorisation (Oklahoma; DC) | v20261114-222418 | **Available, suggestion only** | Transactions: suggested category with confidence and **✓ accept / ✗ reject**, or choose another; Review groups; Model Lab "Try it" with the n-grams that drove the prediction | 0.600 / 0.585 macro-F1; ~44% confident agreement on Indian-format narrations |
| Anomaly Detection Scanner (Oklahoma Isolation Forest) | v20261114-222608 | **Available, experimental, not human-validated** | New **Anomaly Scanner** page: scanned count, flags with score and reasons, score histogram with the model's threshold; Transactions page; blinded review | Not fraud; review not complete |
| Cash-Flow Forecasting (MoneyVis XGBoost) | v20261114-215913 | **Available, experimental** | Cash-Flow Forecast: XGBoost forecast shown **next to** the 3-month-average baseline, with the measured MAE £856.93 vs £809.49 | One UK person; less accurate than the baseline in testing |
| Model Lab and provenance | - | Available | Model Lab: status, acceptance checks, metrics, datasets, run details, "Open feature" links | - |
| ULB benchmark | v20261114-220005 | Research benchmark only | Model Lab (labelled "not a Finora feature") | Never Finora's accuracy |

## 2. Test failures: root causes and fixes

At the start of this round, 26 tests were failing. Every one was investigated; none was skipped, and none had its assertions removed without a replacement.

| Class | Tests | Root cause | Fix |
|---|---|---|---|
| **Real regression (fixed in the app)** | `test_statement_fixes` c1 / regular-credit / ATM, `test_statement_import` insights tests | `intelligence._merchants` crashed (`IndexError`) when a merchant's rows had no category | Missing categories become an explicit "Uncategorised" bucket in the derived frame |
| **Real regression** | (found while fixing the above) | An uncategorised *credit* was treated as a refund and reduced spending | Uncategorised credits count as neither refunds nor spending |
| **Real regression** | `test_statement_import::review_queue` | The review queue grouped only the 300 newest rows, so groups were partial and "apply to group" missed rows | Groups are built from all review rows; `refs` lists every row; the UI applies to all |
| **Real regression** | (found in review) | The PDF said "0 transactions flagged" when detection was off; peer ratios were printed as "%"; peer sizes counted stacked records | Fixed in `report.py` / `peers.py` |
| **Real regression** | (found in review) | No-model rows were stamped `category_source="model"`, and missing confidence (NaN) skipped review; the Transactions dropdown showed the first category for uncategorised rows; the Review page would crash on a null `classified_as` | Fixed in `records.py`, `statement_classify.py`, `Transactions.jsx`, `statements.py` |
| **Obsolete synthetic-model assumption** | `test_api::planted_anomalies`, `test_statement_import::ground_truth`, `test_records::categorised_by_model`, `test_api::full_lifecycle` categories, `test_api::model_lab` | Asserted the synthetic model's results on its own synthetic narrations or planted anomalies | Rule-based classes and every money total stay **exact**. Merchant rows must be a model decision with confidence recorded, or explicitly left for review. Indian merchant accuracy is not asserted (no claim is made) |
| **Changed ML output (by design)** | `test_demo_regression` ×4 | New real models change `ml.*`, recommendations and alerts | 700+ non-ML values still compared **exactly**. New test: fed the golden ML outputs, today's recommendation and alert engine reproduces the golden output **exactly** |
| **Missing-model behaviour** | `test_api::health`, `test_records` ×2, `test_sandbox`, `test_statement_import::import_flows`, `test_partial_profiles` | Assumed every model is active | Health equals the set of active models. Inactive models report `available: false, model_status: awaiting_approved_model`. The anomaly behaviour test loads the trained (inactive) artifact directly |
| **Test defect** | `test_partial_profiles` chat | The `None` detector matched the word "none" in "none stand out" | Answer reworded; it now also says "US households" |
| **Test defect** | `test_reports` | A PDF size over 20 kB stood in for "complete" | Now asserts all 12 section headings, the not-active wording and the scope notes (uncompressed PDF) |
| **Security inventory** | `test_route_security` | The new review `PUT` route was not in the known-mutations list | Listed: full session required, writes only the caller's label |

**Final (after the visibility changes): 408 passed, 0 failed, 0 skipped** (`pytest` exit code 0). The two model gates that used to skip for inactive models now
check those models' latest trained versions. Frontend `npm run build` succeeds.

New tests:
- `test_phase6_models.py`: registry, activation refusal, acceptance, deactivate and rollback, never-train-on-start, blinding, reviewers and kappa, estimator validity.
- `test_peers_verification.py`: households, weights, population, cluster sizes, weighted percentiles, stability, the 8 Finora features, descriptions.

## 3. Registry and rollback

Each of these is checked by a test:
- **Activation refusals.** Activation is refused for:
  - synthetic data, an unevaluated or unapproved version;
  - a tampered artifact or a checksum mismatch;
  - a benchmark;
  - any version that fails its acceptance criteria (the forecast and anomaly models are both refused live).
- **Loading:** a checksum mismatch at load raises `ModelUnavailable`. There is no fallback, and the app never trains on its own.
- **Deactivate and rollback** restore the previous entry exactly, with history kept.
- **Legacy:** the legacy artifacts are byte-identical to their recorded checksums (`artifacts/legacy-synthetic-2026-11-13/README.md`) and load only with `MODEL_SET=legacy-synthetic`.

## 4. Data completeness

All raw files match their recorded SHA-256s:
- Oklahoma: 48 files covering 48 months, each month once, with 0 cross-file duplicates.
- DC, ULB, MoneyVis, UCI: 1 file each.
- SCF: 2 files.

Original raw files are kept unchanged in `datasets/raw/`; processed files are separate in `datasets/processed/`.

## 5. Browser walkthrough (local, throwaway test account)

- **Model Lab** shows each model's status, label, deployment policy, acceptance checks with values, metrics, datasets and run details, and the AI CFO mismatch.
- **Blinded review page:**
  - shows 300 items and the cardholder's history;
  - the live API response contained none of `score`, `model_flag`, `rule_flag`, `stratum`, `selection_probability` or `hidden`;
  - **no label was submitted**.
- **Transactions** says detection is not active, **Forecast** says no approved model exists and why, and **Plan, Insights and Review (Phases 4 and 5)** load with no console errors. The Plan figures are unchanged (health score 95, surplus ₹61,998).

## 6. Database, backups and environment

- **Development database:**
  - integrity `ok`;
  - compared with the backup taken just before the migration: **0 pre-existing rows missing or changed in any table**;
  - one new table, `anomaly_review_labels`, with 0 rows. It can be reversed with `DROP TABLE anomaly_review_labels`.
- **Added rows:** these come only from the throwaway local account `phase6-check-7f3a@tests.finora.invalid`, which has 1 session and 2 audit events.
  - It opened one demo sandbox (`SB_712703B50443E351`, 554 copied demo transactions).
  - That sandbox is owned only by this account and is deleted automatically 24 hours after creation.
- **Backups:** all pass `pragma integrity_check`: before-phase1, 3, 4, 5, before-phase6-review-table, and `~/finora-backups/2026-11-14-before-move`.
- **`.claude/`:** untracked (`??`), with 0 files in git.
- **`~/Desktop/finora`:** untouched. No file there is newer than the start of Phase 6, including its Vite cache.

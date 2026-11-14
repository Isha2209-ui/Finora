# Finora: verification log, Phase 4 (Large-Scale Financial Statement Intelligence)

Recorded 14 Nov 2026 on the development Mac. The project now lives at `~/Developer/finora`; it was moved out of the
iCloud-synced Desktop first (see "Before Phase 4"). Every entry states what was checked, how, and the result,
including what failed first.

## Before Phase 4
| Check | How | Result |
|---|---|---|
| Phase 3 merged | `git merge --ff-only phase-3-manual-entry` into `master` | Fast-forward. The merge diff showed that iCloud had also renamed `backend/app/data/seed.py` to `seed` in an earlier commit (content unchanged; no test imports it). Restored in a new commit, `fe21635`; history not rewritten. |
| Backup before the move | `~/finora-backups/2026-11-14-before-move/`: SQLite online backup, `git bundle --all`, project archive, SHA-256 manifest | DB `integrity_check` ok; all 26 tables have identical row counts (244 profiles, 327,196 transactions); bundle verifies and clones to `fe21635`; archive extracts and matches all 393 files byte for byte |
| Copy to `~/Developer/finora` | `ditto`, then manifest comparison | All 393 project files identical; venv (14,740 files) and node_modules (12,662) copied in full. The venv's scripts still pointed at the Desktop path; rewritten in the new copy (only `.pyc` debug strings still mention the old path) |
| After the move | `git fsck --full`, DB integrity, load all 5 model artifacts, `.env` keys present (no absolute paths), full tests, build, `run.sh` startup | fsck ok; integrity ok; all artifacts load; 271 passed (rc=0); build ok; API and web answer, and the server's working directory is in `~/Developer` |

The original `~/Desktop/finora` was **not** deleted. Note: the desktop app's preview launcher still started the frontend
from the Desktop copy during this phase (found in the browser check below); it was stopped and the server run from `~/Developer`.

## What was built
- **`statement_parser.py`**
  - Reads UTF-8, UTF-16 and Windows-1252 files; comma, semicolon, tab or pipe separated.
  - Finds the header row under bank header lines and skips footer and summary lines.
  - Recognises column roles by name in any order. If none can be recognised, it shows the columns and asks the person to map them.
  - Infers the date format from the data; handles amounts in Indian or Western grouping, `Rs.`/`₹`, `(500)`, `500-`, `500 Cr`/`DR` and Dr/Cr columns; puts newest-first files into date order.
  - Repairs unquoted thousands separators only when exactly one reading fits the columns.
  - Reconciles every running balance against the previous one ± the amount.
- **`statement_classify.py`**
  - Each row is decided by the first of these that applies:
    1. the person's remembered corrections;
    2. a category column in the file;
    3. structural rules: own-account transfers (own last digits, SELF/OWN A/C, or an equal and opposite row in another own account within 3 days), card bill payments and payments received, refunds matched to the original purchase, salary (wording, or the largest steady monthly credit), interest, dividends, cashback, fund redemptions;
    4. the **trained Transaction Categoriser** (the existing TF-IDF + logistic regression artifact), with its probability stored per row.
  - Credits from unrecognised senders are **not** counted as income until the person confirms them.
- **`statement_import.py`**
  - Flow: preview, then confirm, then a background run with a live stage and percentage (read, parse in 10k chunks, categorise distinct narrations in 5k chunks, patterns, duplicates, save in 2,000-row commits, pre-compute the analysis).
  - Cancel, undo (rows removed, previous balance restored), cleanup of saved rows on any failure, and rollback of imports interrupted by a server restart.
- **Duplicates.** A row already stored for the same account or card (same date, amount, direction and narration) is skipped. Matches are counted, so genuine identical rows in one statement are kept.
  - Same-file re-import is warned before it starts, and overlapping statements in a different layout add nothing.
  - Rows that look like a hand-entered transaction are kept but flagged for review.
- **Balances.** An account balance changes only from a statement whose running balances reconcile (at least 98% overall and the last rows), is stored with its as-of date and `balance_source = "statement"`, and the person can decline it. Editing the balance by hand turns it back into "manual". Card statements never set an outstanding amount. Investment debits are reported as cash flows, never turned into holdings.
- **Review and corrections.**
  - Uncertain rows are grouped by counterparty.
  - One decision fixes a whole group and can move rows between the income and spending tables.
  - "Remember" stores a rule that applies to future imports before the model is consulted.
- **Statement Intelligence** (`/api/profiles/{id}/insights`, page `/insights`). Works for demo sandboxes, manual and imported data, filterable by account, card and period. It shows:
  - where the money goes, and how spending changes month to month, with income alongside;
  - recent vs previous months and year over year;
  - the largest merchants and recurring commitments (cadence, next date, "Add to My Data");
  - investment cash flows and income patterns (salary regularity, usual day, raises);
  - unusual spending, labelled as not fraud detection.
- **Pages:** Import Statements (`/statements`), Review & Corrections (`/review`), Statement Intelligence (`/insights`). The old one-shot `/upload` endpoint still works through the new pipeline.
- **Schema (additive):**
  - `transactions`: `import_id`, `balance_after`, `confidence`, `needs_review`, `review_reason`, `flags`.
  - `income_records`: `import_id`, `raw_description`, `classified_by`, `confidence`, `needs_review`, `review_reason`.
  - `bank_accounts`: `balance_as_of`, `balance_source`.
  - New tables `statement_imports` and `category_rules`.
  - SQLite busy timeout set to 30 s.

## Tests
`backend/tests/test_statement_import.py`: 36 tests.

The statements are **synthetic** (`tests/statement_fixtures.py`): two years for one fictional person in six layouts that imitate the column headers of common Indian bank exports. They are not real bank files. Every row carries its true class.

| Area | Result |
|---|---|
| Five bank layouts (HDFC-, SBI- newest-first + tab, ICICI-, Kotak- semicolon + Dr/Cr, generic signed) | Every row read with the right date, amount and direction; closing balance verified and equal to the truth |
| Card layout with `Cr` marks | Payments and refunds read as credits |
| Classification vs ground truth (two-year bank file, 545 rows) | 545/545 correct |
| Classification vs ground truth (card file, 267 rows) | 267/267 correct, after the fixes below |
| Effect on the analysis | Average monthly income and expenses equal hand-computed truth to the paisa (card bills, transfers and investments excluded, refunds subtracted). Net worth moves by exactly the balance change. Health score, FIRE, tax and forecast become available. Every imported spend is scored by the anomaly model. The PDF report renders. |
| Intelligence | Rent ₹25,000 and EMI ₹15,000 × 24 months; Netflix monthly and active; SIP as an investment commitment; salary 24/24 months, day 1, raise ₹95,000 → ₹1,05,000 detected; card filter shows card rows only |
| Duplicates | Same file is refused, then adds 0 with 545 skipped; overlapping 6 months in another layout add 0; three identical same-day metro fares are kept; a hand-entered look-alike is flagged |
| Malformed and partial files | Empty, binary, 2-column and non-statement files are rejected with a reason. Bad dates, blank or text amounts and wrong-width rows are counted by reason. Row and size limits apply. A file without balances never sets a balance. A corrupted balance column is not trusted. A new account needs a verified or typed balance. Column mapping can be done or corrected by the person. |
| Corrections | 8 unrecognised credits moved to income raise average monthly income by exactly their total ÷ 24. The remembered rule classifies the next import from that sender with no review. Income can be moved back to transfer. A category change moves spend between categories exactly. A debit cannot become income. |
| Undo, cancel, failure, restart | Undo restores net worth and cash flow exactly. A cancelled import saves nothing. A failure after rows were saved leaves no rows and the original balance. An interrupted "running" import is rolled back at start-up. |
| Ownership | Another account gets 404 on every import, review and insights route and cannot reach rows by id. Demo templates refuse imports (403) but their insights can be read. Sandboxes have the same features, and Reset removes their imports. |
| Scale | 150,000 rows (15.3 MB) imported with progress through every stage; 75+ save chunks; closing balance verified and exact |

**Totals:** 307 backend tests passed (pytest rc=0), and the frontend build passes. The demo golden-file regression and the route-security audit still pass.

### Timings (this Mac, 150,000-row file)
| Step | Time |
|---|---|
| Preview | 1.0 s |
| Import | 9.6 s (about 15,800 rows/s; 14,921 distinct narration shapes scored) |
| Full analysis afterwards | 13.4 s, now pre-computed in the import's last stage |
| Insights | 3.7 s |
| Transactions page | 1.9 s |
| PDF report | 2.3 s |

A typical two-year personal statement (about 550 rows) imports in under 0.3 s.

## Failures found during Phase 4, and fixes
1. **Card credits were read as debits.** Only about 10% of rows carried a `Cr` mark, below a 30% threshold, so payments and refunds would have counted as spending. Any Cr/Dr mark on a non-negative amount column is now used.
2. **Layout mislabelled.** A generic signed-amount file was called "Kotak-style", and `Amount (in Rs.)` was not normalised. The label threshold was raised and the header normalisation fixed. Parsing never depended on the label.
3. **Refunds not matched to purchases.** "REFUND" was part of the counterparty name. Refund words were added to the merchant-name stoplist; all refunds now match.
4. **Only 56,463 of 150,000 rows imported in the first stress test.** My fixture wrote `1,234.56` unquoted in a comma-separated file, and those rows were dropped as malformed. Real exports do this too, so an unambiguous repair was added. Rows still ambiguous are dropped and counted. With the gaps, the balance correctly refused to verify (37.8% reconciled).
5. **Merchant table crashed.** `r.count` is a pandas method; fixed.
6. **Row limit could not be changed at runtime.** The limit was bound at function definition; it is now read at call time.
7. **A file with unrecognised headers was rejected outright.** It now opens the column-mapping editor instead.
8. **Blank debit and credit cells were reported as "zero amount".** They are now "no valid amount".
9. **Two of my test assumptions were wrong:**
   - "transfers" was expected to include unrecognised credits; those are counted separately by design.
   - An anomaly-count threshold of 700 was a guess; the test now uses the model's real scoring filter (587 rows).
10. **Browser:**
    - The import result's "Biggest spending categories" listed card bills, transfers and investments. These now appear separately as "money moved, not spent".
    - A bank file without balances showed an empty Balance box; it now says why nothing changed.
    - The filter dropdowns stretched full width.

## Browser walkthrough (built-in browser, local servers from `~/Developer/finora`)
- Created a throwaway account and a private profile with HDFC ••1234 (₹50,000), SBI ••7788 (₹80,000) and a Millennia card ••4321 (₹12,000 outstanding).
- **Two-year HDFC-style file, dropped on the upload zone.**
  - Preview: HDFC-style, 24 months, 500 debits and 45 credits, balances reconcile 100%, closing ₹2,29,475 on 27 Oct 26.
  - Import: 513 transactions and 32 income records (salary ₹24.00 L, interest ₹4,104); 8 unrecognised credits went to review; 468 rows decided by the ML model and 77 by rules; the verified balance was applied.
- **Two-year card statement:** recognised as a card statement; 267 rows attributed to the card; 24 payments as card payments and 4 refunds; outstanding left as entered.
- **Last 6 months in an SBI-style, newest-first, tab-separated layout:** 0 added, 137 skipped as already imported.
- **Unrecognised headers ("When, What, Out, In"):** the mapping editor opened; after mapping, 2 rows were imported to SBI as Dining and Travel.
- **Review:** one group, "Rahul Sharma" × 8, with its reason shown. Marked as Transfer with "remember"; the queue emptied and the rule was listed.
- **Statement Intelligence:** every figure listed in the Tests section was visible and matched.
- **Checked by hand before undo:**
  - Net worth ₹2,97,475.08 = ₹2,29,475.08 + ₹80,000 − ₹12,000.
  - Average income ₹1,00,170.99 = (₹24,00,000 + ₹4,104) ÷ 24.
- **Undo from the history table:** HDFC back to ₹50,000 "manual"; net worth ₹1,18,000; income back to "not known"; the import shown as undone.
- The test account, its profile and the temporary files were deleted afterwards. The database is back to 4 templates and 240 population profiles, with 0 accounts.

## Model and data provenance for this phase
- No model was retrained in Phase 4. Imports use the existing categoriser artifact (`backend/artifacts/categoriser.joblib`, sha256 prefix `d7e83205fae8`).
- That model was trained on **synthetic** narrations from `app/data/narrations.py` (15 templated statement formats, 3 held out for evaluation). Its metrics are in Model Lab.
- The 100% accuracy above was measured on synthetic statements built from those same templates. **It says nothing about accuracy on real bank files, which has not been measured.** Low-confidence results and unrecognised credits are routed to review for that reason.
- Local retraining of every model with full provenance is Phase 6.

## Known limitations
- Merchant names are heuristics from the narration text, so some read awkwardly ("Emi", "Atm Wdl", "Bse Star").
- Salary is inferred from wording or steady monthly credits. Irregular freelance income will mostly land in review rather than be counted automatically.
- Months at the start or end of a statement can be partial; Statement Intelligence lists them, but monthly averages include them.
- Import progress is held in the server process. A multi-worker deployment would need shared progress storage (Phase 11).
- CSV only; PDF and XLS statements are not supported.

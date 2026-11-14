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
- **Duplicates** (revised after the independent audit, see below).
  - A row already stored for the same account or card is skipped when the date, amount and direction match and the narration is identical or a shortened form of it. Each stored row absorbs at most one incoming row, so genuine identical rows are kept, and since the audit they are also counted in every figure.
  - Other rows on the same day with the same amount and direction are kept and flagged for review, whether they were entered by hand or imported.
  - Same-file re-import is warned before it starts.
  - If the preview finds that at least half the file already exists on a different account or card, importing to the chosen one needs explicit confirmation.
- **Balances** (revised after the audit). An account balance changes only from a statement whose running balances reconcile (at least 98% overall and the last rows), and it is stored with its as-of date and `balance_source = "statement"`.
  - A balance the person typed is replaced only if they explicitly tick "replace".
  - A statement-verified balance is refreshed by a newer verified statement unless declined.
  - Undo restores the balance in any order of imports and undos. Editing the balance by hand turns it back into "manual". Card statements never set an outstanding amount. Investment debits are reported as cash flows, never turned into holdings.
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
| Duplicates | Same file is refused, then adds 0 with 545 skipped; overlapping 6 months in another layout add 0; three identical same-day metro fares are stored (and, since the audit fixes, counted; see `test_statement_fixes.py`); a hand-entered look-alike is flagged |
| Malformed and partial files | Empty, binary, 2-column and non-statement files are rejected with a reason. Bad dates, blank or text amounts and wrong-width rows are counted by reason. Row and size limits apply. A file without balances never sets a balance. A corrupted balance column is not trusted. A new account needs a verified or typed balance. Column mapping can be done or corrected by the person. |
| Corrections | 8 unrecognised credits moved to income raise average monthly income by exactly their total ÷ 24. The remembered rule classifies the next import from that sender with no review. Income can be moved back to transfer. A category change moves spend between categories exactly. A debit cannot become income. |
| Undo, cancel, failure, restart | Undo restores net worth and cash flow exactly. A cancelled import saves nothing. A failure after rows were saved leaves no rows and the original balance. An interrupted "running" import is rolled back at start-up. |
| Ownership | Another account gets 404 on every import, review and insights route and cannot reach rows by id. Demo templates refuse imports (403) but their insights can be read. Sandboxes have the same features, and Reset removes their imports. |
| Scale | 150,000 rows (15.3 MB) imported with progress through every stage; 75+ save chunks; closing balance verified and exact |

**Totals before the audit:** 307 backend tests passed (pytest rc=0). **After the audit fixes:** 327 passed (rc=0), and the frontend build passes. The demo golden-file regression and the route-security audit still pass.

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


## Independent audit (round 1) and fixes

A separate checker with no part in building Phase 4 audited branch `phase-4-statements` at `7cccd81`. Its verdict was **FAIL**: 7 critical and 10 minor findings, each reproduced with its own scripts, API calls and database queries. Every finding was confirmed against the code before fixing. One leftover file from its run (`backend/uploads/pending/import_28.csv`, 3,005,987 bytes, synthetic "ACME CORP" rows) was checked and deleted.

| # | Finding (audit) | Cause | Fix | Regression test (`tests/test_statement_fixes.py`) checks |
|---|---|---|---|---|
| C1 | Two identical same-day purchases were stored but counted once (Travel Rs 800 instead of Rs 1,600) | `clean_transactions` de-duplicated on date, amount, narration, account, card, type | `ref` added to the key. Stored rows have unique refs, so real repeats count; raw rows without a ref are still de-duplicated. The live data has 0 rows affected, so the demo golden file is unchanged. | Travel total Rs 1,600; average monthly expenses Rs 3,400 |
| C2 | Overlaps with shortened narrations doubled salary; the same file on another account was double-counted silently | Matching required the exact narration; overlap checked only within the chosen target | Three passes: exact, shortened narration, look-alike flagged. The preview reports overlap per account or card, and starting into a different target needs `allow_overlap`. | Income and expenses unchanged after a truncated re-import; 409 for another account or a new account; imported look-alike flagged |
| C3 | A Rs 600 Swiggy debit became a "transfer" because a friend's Rs 600 arrived elsewhere the same day | Pairing used only amount, direction and date | Pairing needs the other side to be a transfer; a debit must also not be a confident purchase (model probability < 0.6, or predicted transfer or card payment) | Swiggy stays Dining and Rs 600 counts as spending; a genuine self-transfer still pairs |
| C4 | Cancel or crash during "Refreshing your analysis" deleted the rows but left the statement balance, a stale analysis and the file; undo was impossible | Cancel was honoured after the balance commit; recovery restored nothing | Rows are saved in chunks; then the balance and summary are written in one commit. After that, cancel is refused ("use Undo") and crash recovery marks the import done. Before it, recovery removes the rows, any created account and the file; the balance was never touched. The failure path invalidates the cache. | Cancel at 97% leaves a complete, undoable import whose net worth matches; a crash mid-save leaves balance, rows, account and file as before; a crash after commit is finished and undoable |
| C5 | Undoing the import that created an account deleted a later import's income and the account | Undo deleted all income on the account | Undo deletes only rows with its `import_id`. A created account is removed only if no row and no other finished import uses it. | The later import's income (Rs 1,00,500) and the account survive |
| C6 | An older statement replaced a balance the person typed, by default | `update_balance` defaulted to true; the guard covered only statement-sourced balances | Tri-state choice: a typed balance is replaced only with explicit consent. The UI box is unticked by default for typed balances and explains what it replaces. | Rs 3,33,333 kept and net worth unchanged unless asked; applied when asked |
| C7 | Undo A then B left A's (undone) balance | Undo restored the stored "previous balance" blindly | Each applied balance records which import supplied the balance it replaced. Undo restores it, or, if a later import already replaced it, re-links that import to the earlier balance. | Both undo orders end at Rs 3,33,333 "manual", and net worth matches |

**Minor findings:**
- **Preview closing balance:** taken from row 2,000. Fixed: the preview reads the whole file.
- **Second salary:** a large regular credit could become a second "salary", giving a false "+68% raise". Fixed: in months that already have salary it is "Other income", flagged.
- **Review count:** "Apply to N" could change more rows than N. Fixed: exactly N; "remember" covers future imports.
- **Income moved to spending:** now asks for confirmation.
- **Invalid date format:** now a clear 422.
- **ATM label:** ATM withdrawals were listed as a recurring "bill". Fixed: cash is excluded, and "bill" now means rent, utilities, insurance or education; other repeats are "regular spend".
- **App's sample file:** did not reconcile (91.2%) because rows were not in date order. Fixed.
- **97% progress:** the analysis stage now explains what is happening and shows elapsed seconds; Cancel is hidden there.
- **Reused account number:** history kept a reused account id. Fixed: the history shows the label captured at import time, and created accounts used by other imports are never deleted.
- **Leftover uploads:** now deleted with the profile, at start-up when no preview is waiting, and when previews expire (24 h).
- **Upload size:** ~~a chunked upload is still capped by the endpoint while reading~~ **incorrect**: the second audit showed a chunked body was spooled to disk in full first, even when not signed in. Fixed in the release round below.

**One mistake of my own was caught during the fix round.** An inline comment swallowed the `new_account` option, so accounts created from a statement were silently not created. Found by the new C5 test before commit, and fixed.

**Results after the fixes:**
- `test_statement_fixes.py` 20 passed and `test_statement_import.py` 36 passed.
- Full suite 327 passed (rc=0), including the demo golden file and the route-security audit; frontend build passes.

**Browser checks after the fixes** (local servers from `~/Developer/finora`, throwaway account, synthetic files):
- The preview read the whole file (all 544 balance rows reconciled).
- On a typed-balance account the replace box was unticked by default with a plain explanation; importing kept Rs 50,000 (net worth Rs 1,30,000 = 50,000 + 80,000).
- The same statement aimed at the SBI account showed "545 of these rows (100%) are already recorded on HDFC Bank XXXX1234" and Import stayed disabled.
- The app's sample statement reconciled at 100%.
- "Apply to 8" sent exactly 8 rows.
- Recurring commitments no longer list ATM withdrawals.
- Undo from the history table returned income to "not known" with net worth unchanged.
- Test data was removed afterwards: 0 accounts, 4 templates, 240 population profiles, 0 imports, no pending files.

**Still open, stated plainly:**
- Merchant names are heuristic.
- Real-bank classification accuracy is unmeasured (synthetic templates only).
- CSV only.
- The analysis stage of a 150k-row import still takes about 15 s; it is explained on screen, not shortened.
- These fixes have **not yet been independently re-audited**.


## Second independent audit and the release-blocker round

A second checker, separate from the first and with no part in building Phase 4, audited `b43719c`. Its verdict was **FAIL**.
- **Confirmed fixed:** C1, C4 and C6.
- **Still failing in variants:** C2, C3, C5 and C7.
- **New critical findings:** A–F below.
- **Not driven:** the browser.

That audit also found that **the test suite was deleting audit records from the development database** (81 → 72). The cleanup deletes audit rows by account id, and SQLite reuses ids. One focused repair round was authorised.

| Audit finding | Fix | Regression test (`tests/test_statement_release.py`) |
|---|---|---|
| **A** Double counting via previews taken before another import, two imports started together, overlap under 50% into another account, and look-alikes with a prefix or 11-character cut | Duplicates are re-checked against the database when the import **runs**, against every account and card including for new accounts. Rows already on another account are skipped and reported (`already_on_other_accounts`) unless the person explicitly chose to import anyway. Imports are serialised per profile (an in-process lock plus a 409 while another import of the profile is alive). Narration matching uses letters and digits containment (≥ 8 characters), so prefixes and cut-off text match. The preview notes partial overlaps. | Stale previews into SBI or a new account add 0 and income stays Rs 90,000. Two imports run in parallel threads add salary once. A 33% overlap skips exactly the 8 shared rows (income total 6 × 90,000). Prefixed and 11-character narrations add 0. |
| **B** Low-confidence debits became transfers by pairing with an unrecognised credit; one credit paired with four debits | Only a **recognised** transfer (rule, file or the person) is evidence; credits parked as "unrecognised" never are. Pairing is one-to-one. | Four unsure Rs 600 debits (at least one below 0.6 confidence) stay spending (expenses Rs 2,400). A recognised transfer pairs with at most one row. |
| **C** Undoing both the creating import and a later one left the undone statement's balance on an empty account | Undoing the creating import marks later imports as having "no legitimate prior balance". After any undo, an account created by an undone import that nothing uses is removed. | The account is gone and net worth equals the profile before either import. |
| **D** Undo deleted another user's account that had received a reused id | Before deleting, undo checks **owner + bank name + masked number** recorded at creation. Deleting an account in My Data detaches it from the imports that reference it. | User 2's Rs 7,77,777 account and user 1's new same-named account both survive; user 2's net worth stays Rs 7,77,777. |
| **E** Chunked uploads (no Content-Length) were spooled in full, even unauthenticated (1,000 MB in 1.9 s) | An outermost ASGI guard on the two upload paths, before any byte is read: no session cookie → 401; no Content-Length → 411; Content-Length over the limit → 413. The server rejects a body longer than its declared length. | A chunked body → 411, anonymous → 401, a 100 MB declared length → 413; the endpoint is never reached (`read_limited` patched to fail) and no import row is created. |
| **F** A second server process rolled back the first's live imports; cancel and progress were invisible across processes | Each import writes a **heartbeat** and **progress** to the database (at least every 2 s and at each stage). Recovery only touches imports whose heartbeat is older than 120 s. Cancel is a database flag read at every stage boundary and heartbeat. Status falls back to the stored progress. | A new process's recovery leaves a live import (fresh heartbeat) and an already-undone import untouched and rolls back only the stale one. A cancel set "in another process" stops the run; balance and rows are untouched. |
| **Test isolation** | `tests/conftest.py` copies the dev database **read-only** (SQLite online backup) into a temporary folder, together with the model files, reports and upload folders, before the app is imported. The suite writes only there, and the folder is deleted at the end. | `test_suite_runs_on_a_temporary_copy_never_the_dev_database`. The dev `finora.db` SHA-256 and audit count were identical before and after the full run. |

The earlier C1, C4 and C6 tests (`test_statement_fixes.py`) still pass. The three recovery tests now age the heartbeat to simulate a dead process.

**Results of this round:**
- Full suite **340 passed, rc=0**.
- Development database byte-for-byte identical before and after the run (SHA-256 `7dc682ec334d548b…`, audit rows 72 → 72).
- Frontend build passes.

**Browser walkthrough** (built-in browser, servers from `~/Developer/finora`, throwaway account, synthetic files):
1. **Import (two years, HDFC):** the replace-balance box was unticked by default; I ticked it on purpose. The import added 513 transactions and 32 income records (salary Rs 24.00 L, interest Rs 4,104), with 8 rows sent to review.
2. **Totals:** net worth Rs 3,09,475.08 (= 2,29,475.08 + 80,000) and average income Rs 1,00,170.99, both exactly as calculated by hand.
3. **Overlap guard:** a 3-month SBI-layout file aimed at SBI showed "68 of these rows (100%) are already recorded on HDFC Bank XXXX1234" and Import stayed disabled.
4. **Cancel:** a 150,000-row file was cancelled at "Categorising 22%". The result was "Import cancelled; nothing was saved": 0 rows in the database, SBI still Rs 80,000, no pending file.
5. **Review:** the 8-row group was classified as Other income. Average income rose by Rs 290.35 (= Rs 6,968.40 ÷ 24) and the queue emptied.
6. **Undo:** HDFC was back to Rs 50,000 "manual", net worth Rs 1,30,000, income "not known".
7. **Cleanup:** the account and profile were removed afterwards (their 13 audit records were kept). Integrity ok; financial row counts identical to before; 0 imports, 0 pending files.

**Remaining limitations (not release blockers by the audits' criteria, stated plainly):**
- **Look-alikes on the same account:** rows with the same date, amount and direction but genuinely different narration text are still **counted until reviewed**; they are flagged.
- **Concurrent starts:** imports are serialised per profile. Only one server process may use a database (see Phase 4 closure below).
- **Crashed imports:** they are recovered once their heartbeat is 120 s old (at start-up or when import status is read), so a crashed import can show "running" for up to 2 minutes.
- **Analysis time:** the stage after a 150k-row import takes about 13–16 s; it is explained on screen.
- **Accuracy:** real-bank classification accuracy is unmeasured; only synthetic templates were tested. Merchant names are heuristic.
- **Format and upload method:** CSV only. An upload must declare its size, which browsers and the app's own client always do.
- **Not re-audited:** this round has not been independently re-audited.


## Phase 4 closure (final targeted checks)

Only two areas were checked, as requested. No broad audit.

1. **Immutable account identity for undo.**
   - **The problem:** SQLite reuses a deleted row's integer id, which is how an undo could reach another user's account.
   - **What changed:** every bank account now gets a random, never-reused `uid` (new nullable column; existing rows were not rewritten). An import records the `uid` of the account it creates. Undo deletes an account only if the **owner and the `uid` both match**. Sandbox copies get their own `uid`.
   - **Tests** (`tests/test_phase4_final.py`):
     - The account is deleted *without* the My Data path, so only the uid can protect it. The test asserts SQLite really handed the same id to user 2's new account with the same bank name and last 4 digits. User 1's undo then leaves it alone: Rs 7,77,777 and user 2's net worth unchanged.
     - Positive control: undo still removes the account it really created, and net worth returns to 0.
2. **One server process per database.**
   - **What changed:** at start-up the backend takes an exclusive OS lock on `<database>.lock` (`app/process_lock.py`). A second process on the same database exits with "Another Finora server process is already using finora.db…", so it can never recover or modify the first process's imports. The OS releases the lock if the process dies. This is a restriction, not multi-process support. PostgreSQL deployments must follow the same one-process rule (documented, not lock-enforced).
   - **Tests:** a child process holding the lock makes `acquire` fail, and the lock is free again after it dies. Two **real uvicorn servers** started on the same database: the second exits non-zero with that message and the first keeps serving.

**Targeted test run:** `test_phase4_final.py`, `test_statement_release.py`, `test_statement_fixes.py` and `test_sandbox.py` gave **48 passed, rc=0**. All tests use the temporary database copy.

**Development database after the checks:** integrity ok, transactions 327,196, audit rows 85 (unchanged by the tests).

**Accepted, non-critical limitations:**
- CSV-only imports.
- Unmeasured real-bank classification accuracy.
- Look-alike rows on the same account counted until reviewed.
- Up to 2 minutes before a crashed import is rolled back.
- About 13–16 s of analysis after a 150k-row import.
- Heuristic merchant names.

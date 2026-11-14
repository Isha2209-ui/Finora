# Finora: verification log, Phase 5 (Finora Plan)

Recorded 15 Nov 2026 on the development Mac, branch `phase-5-plan` (from `master` at `69bd2e5`). The specification is
"Phase 5: Finora Plan, the main page" from the original 11-phase plan. Phase 6 has not been started.

## Before Phase 5
- **Merge:** `phase-4-statements` was merged into `master` by fast-forward (`69bd2e5`), with your approval.
- **New backup:** `backend/backups/finora-before-phase5.db`. Existing backups were not touched.
- **Full suite after the merge:** 344 passed (rc=0) on the temporary test copy. The development database was byte-for-byte unchanged.
- **Build:** passed.
- **Development database:** integrity check ok; 327,196 transactions (Rs 75.99 Cr), 7,434 income records, 475 accounts, 270 cards; identical to the backup.

## What was built (against the specification)

| Specification | Implementation |
|---|---|
| **Financial picture:** income, expenses, surplus, balances, debt and EMI load, net worth, runway, health score, investments, FIRE progress, data completeness | `plan.picture()`. The page shows four headline numbers; "Show the full picture" reveals the rest. Each number has a plain explanation. |
| **Diagnosis:** 3–6 findings, each with finding, evidence, why it matters, model or rule source, confidence or limitation, detail link | `plan.diagnosis()` uses the existing recommendation rules, ordered by severity. The source is labelled as a model estimate or an exact rule. Data gaps fill up to 3 findings when needed. Missing insurance is reported as *not recorded*, never as Rs 0 cover. |
| **Action plan:** 3–5 ranked actions with a specific step, evidence, Rs impact and the effect on surplus, debt-free date, runway, health score and FIRE age | `plan.candidate_actions()` builds concrete steps from the person's own numbers: spending cap on the largest lifestyle category, extra repayment on the highest-rate debt, emergency-fund contribution, SIP (by the 15% guideline or the FIRE gap), and delaying a goal that would drain savings. They are ranked by a published benefit formula. |
| **Accept, Dismiss, Edit, Detail** | API: `POST/PATCH/DELETE /plan/assumptions`, `POST/DELETE /plan/dismiss`, `GET /plan/actions/{code}`, and a read-only `POST /plan/preview` for live editing. UI: one action at a time with Add to my plan, Edit (live preview as you type), Not for me (can be undone) and "How this is calculated". |
| **Accepted actions become rows in a plan-assumptions table** | New table `plan_assumptions` (kind, params, title, source action, status). Kinds: extra debt repayment, spending cap, emergency-fund contribution, SIP, delayed purchase. Assumptions survive restarts. Deleting a profile or resetting a sandbox removes them. |
| **A scenario engine applies the assumptions on top of the unchanged history and recalculates forecast, debt payoff, runway, FIRE and health score** | `plan.evaluate()` is pure: it reads the cached, history-based analysis and adds assumptions in memory. It reuses the existing engines: `simulate_payoff` (avalanche), `health_score`, `fire.project`. Runway and health are measured 12 months ahead. |
| **Accepting never touches source transactions and never pretends a payment happened** | Only `plan_assumptions` is written. The UI states this on every view. |
| **Impact = baseline − scenario, never hard-coded; tests assert it** | `plan.compare()`. Every action carries `effect = compare(evaluate([]), evaluate([action]))`, and the Rs headline is derived from that effect. |

**Design:** the page follows the final design direction:
- It is the landing page and the first navigation item.
- A calm hero sentence, four headline numbers and three guided steps (What we found → What to do → Your plan), showing one action at a time.
- Progressive disclosure: full picture, finding details and a calculation panel are each a click away.
- Contextual explanations on every metric.

Other pages were not redesigned (that is Phase 8).

## Tests (`backend/tests/test_plan.py`, 15 tests; all on the temporary test database)
- **Structure (all 4 demo identities):**
  - the picture fields are present;
  - 3–6 findings, each with all six parts;
  - 3–5 actions, ranked by descending benefit, each with a step, evidence, impact and all five effects.
- **Impact equals baseline minus scenario (all 4 demo identities), re-derived independently:**
  - extra repayment: debt-free months and interest saved equal two direct `simulate_payoff` runs;
  - spending cap: surplus +amount, runway = pool / (expenses − cut), Rs impact = 12 × amount;
  - SIP: FIRE age equals a direct `fire.project` run;
  - emergency fund: pool +12 × amount;
  - and for every action, `effect == compare(baseline, scenario)`.
- **Delayed purchase:** a Rs 1.5 L goal due in 6 months moves out of the 12-month window, so the pool rises by exactly Rs 1.5 L and runway changes accordingly.
- **Accept, edit, dismiss, detail, preview and remove:**
  - the plan scenario equals the engine run with the accepted assumptions;
  - an edit recomputes the debt-free date, and the step title follows the stored amount;
  - dismissing changes no outcome;
  - preview stores nothing;
  - removing everything returns to the baseline.
- **History unchanged:** a SHA-256 fingerprint of every source table (transactions, income, accounts, cards and statements, loans, SIPs, goals, holdings, deposits, other assets, insurance, property, recurring) is identical before and after all of the above. The history-based analysis (cash flow, net worth, liquidity, debt, health, FIRE) is unchanged, and no future-dated transaction exists.
- **Persistence:** assumptions survive cache invalidation; an over-committed plan is flagged.
- **Validation:** zero or extra fields, unknown kind, another profile's goal, an impossible spending cap, and extra repayment with no debt all give 422.
- **Ownership:** another account gets 404 on plan, accept and preview, and cannot edit or remove an assumption by id. Templates are readable (`read_only`) but accept gives 403.
- **Partial data:** an empty profile gets an honest "needs income and spending", no actions and data-gap findings.
- **Reset:** a sandbox reset removes its assumptions.

**Full suite:** 359 passed (rc=0). Development database fingerprint unchanged by the run.

## Failures found during Phase 5, and fixes
1. **The test-database copy was not migrated** when the app's start-up did not run, so the new `bank_accounts.uid` column was missing. Fixed: `conftest.py` runs the additive migration on the copy.
   - My first placement of that migration imported the app *before* the suite's generous rate limits were set, giving 118 failures with "Too many sign-ups" (429). Moved after the settings; 359 passed. The development database was untouched in both runs.
2. **Aarav (healthy) got only 2 actions.** The SIP action now also covers a FIRE-target gap, sized to the gap.
3. **Delayed purchase produced no effect.** The delay kept the purchase inside the 12-month window. It now moves the purchase past the window, or further if affordability needs it.
4. **Empty profile showed "No personal health insurance, cover Rs 0".** The plan's diagnosis now says insurance is *not recorded*.
5. **Browser: the calculation panel opened off-screen.** The page container keeps a transform from its entrance animation; the panel is now rendered in a portal on `<body>`.
6. **Browser: an edited step kept its original title** ("Pay Rs 14,500…" for Rs 25,000). Titles are now generated by the server from the stored amount, on accept and on edit; a test asserts it.

## Browser walkthrough (built-in browser, servers from `~/Developer/finora`, throwaway account, Kabir Singh demo copy)
1. **Landing:** exploring the demo landed on Finora Plan, with 6 findings and 4 steps; the first finding opens with its evidence.
2. **Edit with live preview:** changing the extra repayment from Rs 14,500 to Rs 25,000 updated the numbers before saving:
   - surplus Rs 19,668 (= 44,668 − 25,000);
   - debt-free 30 months sooner (Apr 2035 → Oct 2032);
   - interest saved Rs 8.73 L (vs Rs 6.07 L at Rs 14,500).
3. **Accept:** "Add to my plan" moved on to step 2 of 4; the first progress dot turned green.
4. **Calculation panel:** the emergency-fund step showed the pool Rs 2.05 L → Rs 4.39 L (= + 12 × Rs 19,500), runway 1.35 → 2.88 months, health 49.9 → 54.1, with method notes.
5. **Dismiss:** "Not for me" marked the step dismissed.
6. **Your plan:** compared with carrying on as you are, surplus is −Rs 25,000 a month and debt-free 30 months sooner, with other metrics unchanged; the step reads "Pay Rs 25,000 extra a month on your debts" after the title fix.
7. **History in the real database:** after all of this, the sandbox's transactions (689 / Rs 22,00,674.98), income (25), accounts, loans and SIPs are identical to the template's. Only two `plan_assumptions` rows were added.
8. **Phone width (375 px):** the *existing app shell's* fixed sidebar squeezes the content. The shell is Phase 8 work and is recorded below.
9. **Cleanup:** the account and sandbox were removed (their audit rows kept); 0 accounts, 0 plan rows, 4 templates, 240 population profiles.

## Known limitations (stated plainly)
- **Model simplifications:**
  - Runway and health are projected 12 months ahead.
  - Debt and credit-use pillars are not re-projected.
  - Extra repayment does not change FIRE: freed EMIs after payoff are not reinvested in the model.
  - Goals are counted only when due within 12 months.
- **Independent actions:** each action's effect is measured on its own. Accepted actions are combined in "Your plan" and over-commitment is flagged, but actions are not re-ranked against each other.
- **Ranking weights:** the weights are a published heuristic, not an optimiser.
- **Mobile layout:** the overall app shell is not yet responsive (Phase 8). The Plan page's own layout adapts.

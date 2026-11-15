# Phase 8 verification: application-wide UI/UX redesign and presentation readiness

**Branch:** `phase-8-ui-redesign`. **Uncommitted, unmerged, not pushed, not deployed.**

**Design documents:**
- [critique (initial, mid-review, final)](PHASE_8_DESIGN_CRITIQUE.md)
- [guidelines](PHASE_8_WEB_GUIDELINES.md)
- [theme](PHASE_8_THEME.md)
- [specification](PHASE_8_DESIGN_SPECIFICATION.md)
- [route checklist](PHASE_8_ROUTE_CHECKLIST.md)

**Screenshots:** [`phase8-screenshots/`](phase8-screenshots) holds 39 images: desktop 1440, tablet 768 and mobile 390. **Browser tests:** [`frontend/e2e/`](../frontend/e2e).

## 1. Final status by acceptance category

All results below are from the final code. "Final run" means the last full run of that suite.

| Category | Status | Evidence |
|---|---|---|
| Registration (20 from one IP, duplicate rejected, isolation) | **PASS** | `p8_registration.js` **5/5**; backend tests `test_twenty_consecutive_signups…` and `test_per_ip_signin_cap_counts_only_failed_attempts` |
| Authentication, sessions, protected routes | **PASS** | smoke + registration + responsive (sign-out, protected URL, sign back in) |
| Navigation, tabs, 18 redirects, back/forward, refresh | **PASS** | `p8_smoke.js` **60/60** |
| Financial, data and ML workflows | **PASS** | `p8_functional.js` **43/43** |
| Six ML capabilities identified, explained and working | **PASS** | functional: 5 feature screens with model chip, explainer and real result; overview lists all six algorithms; no development wording |
| Responsive 1440 / 1280 / 768 / 390 | **PASS** | `p8_responsive.js` **55/55**: 10 pages × 4 viewports, no overflow, correct nav form |
| Accessibility checks (automated subset) | **PASS** | one `h1` per page, every button named, every input labelled, skip link, tab arrow keys, visible focus, dialogs with focus trap and Esc, live regions; see §6 |
| AI CFO (local qwen2.5:3b via Ollama) | **PASS** | `p8_ask.js` **12/12** (final full run) |
| Backend regression | **PASS** | **487 passed, 0 failed** |
| Frontend production build | **PASS** | `vite build`; main bundle 350 kB, code-split by area (995 kB before) |
| Console errors / failed API requests | **PASS** | 0 console errors and 0 unexpected failed API requests in every final run |
| Presentation wording audit | **PASS** | no academic, educational, advisory or development-stage wording in the frontend or in AI answers; see §8 |

## 2. Registration and sign-in changes (presentation requirement)

| Before | After |
|---|---|
| 10 sign-ups per IP per hour (`REGISTER_IP_MAX=10`) | **No limit by default** (`REGISTER_IP_MAX=0`). The mechanism remains and is enabled by setting a positive value, for example in a public deployment. |
| Per-IP sign-in cap counted *every* attempt (30 per 15 min) | Counts **only failed** attempts. Password spraying is still blocked; real sign-ins are never blocked. |

**Unchanged:**
- unique e-mails (duplicates rejected: "An account with this e-mail already exists. Sign in instead.");
- argon2id hashing and password rules;
- the per-e-mail lockout after 5 failures;
- httpOnly sessions and CSRF;
- protected routes, profile ownership and isolation.

**Audit result:** there is no CAPTCHA, no e-mail verification gate, no invite-only mode and no approval step, so none needed removing.

## 3. Disclaimers and development labels removed

- **Interface.**
  - Removed: "Academic project · educational guidance only, not licensed financial advice"; sidebar, Home, Plan, Ask and composer disclaimers; the experimental and validation badges and banners; acceptance-criteria headlines; "Unusual is not fraud" banners; "not validated" hints.
  - Backend text that can contain such clauses (finding sources and reasons, model notes) is shown through `present()`. The underlying records are unchanged.
- **AI CFO.**
  - Answers no longer carry the appended disclaimer (`writer.DISCLAIMER` is empty; older saved answers are cleaned on display).
  - Prompts no longer ask for disclaimers. The rule against recommending specific stocks or funds stays.
  - Tool notes now name the model and its basis, for example "Isolation Forest: unusual compared with this person's own history", instead of development-stage caveats.
- **Kept, as factual product statements rather than disclaimers:**
  - the demo-copy indicator (the data is a fictional person's);
  - data provenance (for example "trained on 30,000 real card accounts");
  - "unusual for you compared with your own history" (what the feature measures).
- **Not deleted:** model metadata, versions, provenance, training information, evaluation results and SHAP values stay in the backend and in Model Lab's expandable sections, under neutral headings. Nothing claims validation or certification.

## 4. The six ML capabilities as presented

Each capability shows its feature name, algorithm, purpose, result for the user and an entry point. The "How it works" drawer covers what it looks at, how it works, how to read the result and the data. Technical details are in Model Lab. Source: `frontend/src/components/models.js`, written from `backend/app/ml`.

| Capability | Algorithm shown | What the explanation covers |
|---|---|---|
| Credit Risk | XGBoost + SHAP | 14 payment-behaviour inputs; boosted trees → probability; SHAP contributions per input |
| Peer Benchmarking | K-Means clustering | 8 standardised household ratios; survey-weighted clusters; nearest-centre match; "better than X%" |
| Transaction Categoriser | TF-IDF + logistic regression | character (2–5) and word n-grams; linear classifier with confidence; user accepts or corrects |
| Anomaly Detection Scanner | Isolation Forest | 5 per-person spending ratios; 300 random trees; few splits means unusual; reasons per flag |
| Cash-Flow Forecast | XGBoost regression | lag and ratio features; prediction relative to the 6-month mean; range from test errors; shown beside a 3-month average |
| Model Lab and provenance | all of the above | versions, datasets, training runs, metrics, evaluation checks, review workspace |

## 5. Functional workflows (Playwright, real backend): `p8_functional.js` 43/43

Each check asserts the visible result *and* the API call; changes are re-read after a refresh.
- **Transactions:**
  - search, server sort, pagination;
  - detail drawer with recategorise (PATCH, persisted);
  - **add a transaction** (POST, categorised, persisted) and delete it (confirm modal).
- **Spending:** view switch and period filter (GET /insights?months=3).
- **Plan:**
  - accept and reopen a recommendation (PATCH, persisted);
  - tax compare and validation;
  - **goals:** create (drawer), **edit** (target doubled → backend monthly need recalculated, persisted), progress with the 0% and 7% figures, delete (modal).
- **Future:** what-if verdict (POST /decision), retirement input (POST /fire), payoff (POST /payoff).
- **Risk & Models:**
  - credit scoring form (POST /models/credit-risk/score);
  - categoriser try-it (POST /categorise);
  - Model Lab `?model=` deep link;
  - each of the 5 feature screens has its model chip, explainer and result;
  - the overview lists all six.
- **Data:** synthetic statement import, preview → start → backend `done` → undo (modal).
- **Settings:** profile edit (PATCH, persisted), security activity (GET /auth/activity), honest "unavailable" list.

## 6. Responsive and accessibility: `p8_responsive.js` 55/55

- **Viewports:** 1440×900, 1280×800, 768×1024 and 390×844, across 10 pages (Home, Plan, Transactions, Spending, Future, Risk & Models, Model Lab, Ask, Data, Settings).
  - No horizontal overflow.
  - Labelled sidebar at ≥1280 px, icon rail at 768–1279 px, drawer below 768 px.
  - Exactly one `h1`; every visible button named; every input labelled.
- **Mobile navigation:** the drawer opens, navigates and closes.
- **Keyboard:** the first Tab reaches "Skip to content" and Enter focuses `main`; ArrowRight moves between tabs and updates the URL; focused controls show a visible outline.
- **Profiles:**
  - an empty private profile explains what's missing, with no invented figures;
  - data persists after refresh;
  - a **second, independent account gets 404 on every route** of the first account's private profile, and forcing the id in the browser does not open it;
  - demo and private profiles coexist.
- **Contrast:** every token pair is computed against WCAG AA in [PHASE_8_THEME.md](PHASE_8_THEME.md).
- **Defects found and fixed by these runs:**
  - the account menu was beneath the content (stacking layer);
  - the mobile Ask button had no accessible name;
  - the panel and input shared a duplicate `id`;
  - drawers were clipped by an animated ancestor (now portalled).

## 7. AI CFO: `p8_ask.js` (local qwen2.5:3b via Ollama; no cloud dependency)

Final full run **12/12**:
- the empty state with suggestions;
- the Stop button while streaming;
- progress stages shown ("Understanding your question → Writing the answer → Draft, being checked");
- the final answer with a ₹ figure, "Understood as" and "Figures checked" ("You spent ₹5,764 on dining last month…");
- the `/chat/stream` request;
- a **follow-up in context** ("Dining spending in September 2026 was ₹5,886…");
- **Esc stops** with "Nothing from this answer was saved", and the server message count is unchanged (4 → 4);
- history reload (2 Q&A, no stopped answer);
- simulated backend error shown clearly with the input usable;
- "Ask about this" pre-fills and does not send.

- the header Ask button opens the side panel with the conversation history.

An earlier run failed the panel check because the test read the panel before the history request returned. The test now waits for the history, and the final run passed. No disclaimer appeared in any answer.

## 8. Backend regression

**487 passed, 0 failed.** That is the Phase 7 baseline of 484, plus 1 test for the optional transaction `sort` / `suggested_only` parameters, plus 2 for registration and sign-in behaviour. Four tests were updated, not deleted, because their intended behaviour changed:
- the rate-limit test now proves the limit works *when enabled*;
- two AI CFO tests now assert that answers carry **no** boilerplate disclaimer;
- the tool-note tests assert the model is named and no development wording appears.

## 9. Not executed, and remaining limitations

- **Not executed:**
  - screen-reader testing with a real screen reader (VoiceOver/NVDA); the automated checks cover names, labels, landmarks and live regions;
  - colour-contrast measurement of rendered pixels (tokens were computed instead);
  - Safari and Firefox (Playwright ran Chromium).
- **Unavailable by design:** password change, preferences and password recovery (no backend endpoints). Settings says so.
- **Not built:** charts inside AI answers (the stream does not carry tool results).
- **Light restyles only:** Plan → Priorities / Actions / Your plan, Data → Review and `/models/review` keep their working flows on the new design system.
- **Deployment note:** set `REGISTER_IP_MAX` to a positive value for any public deployment.

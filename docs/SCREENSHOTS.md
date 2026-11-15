# Finora: screenshot checkpoints

All screenshots are in [`phase8-screenshots/`](phase8-screenshots): 83 PNGs.
- **`p9-*` (44):** the Phase 9 real-browser walkthrough of the merged application, captured by [`frontend/e2e/p9_walkthrough.js`](../frontend/e2e/p9_walkthrough.js) and [`p9_debt_edge.js`](../frontend/e2e/p9_debt_edge.js) at 1440×900. Each was captured during a scripted step whose check passed; several checks compare the figures on screen with the API that produced them.
- **Unprefixed (39):** the Phase 8 design screenshots at desktop 1440, tablet 768 and mobile 390, captured by `p8_responsive.js`.

Data shown is the demo person *Aarav Mehta* (synthetic, labelled "demo copy") unless stated.

Legend: **I** initial screen · **A** user action · **R** successful result · **E** validation or error state.

## Phase 9 walkthrough (1440×900)

| # | File | Area | Kind | What it demonstrates |
|---|---|---|---|---|
| 1 | `p9-01-sign-in.png` | Sign in | I | Split sign-in screen |
| 2 | `p9-02-sign-in-validation-error.png` | Sign in | E | Empty submit gives an inline "Enter an e-mail address" error |
| 3 | `p9-03-registration-filled.png` | Registration | A | Create-account form filled (name, e-mail, password with show/hide) |
| 4 | `p9-04-onboarding-start.png` | Onboarding | R | New account greeted by name; choice of demo person or own profile |
| 5 | `p9-05-home.png` | Home | R | Answer-first Home: status sentence and top priorities with reasons |
| 6 | `p9-06-plan-priorities.png` | Plan | I | Diagnosis and ranked priorities |
| 7 | `p9-07-goals-initial.png` | Goals | I | Progress per goal; on-screen monthly amounts at 7% and 0% equal the API (₹38,505 / ₹40,000 for the car) |
| 8 | `p9-08-goals-validation-error.png` | Goals | E | Past target date refused: "Target date must be in the future", shown **inside** the drawer (Phase 9 fix) |
| 9 | `p9-09-goals-add-drawer.png` | Goals | A | Add-goal drawer with a valid date |
| 10 | `p9-10-goals-result.png` | Goals | R | New goal saved (POST 201); its ₹19,366 / ₹20,000 a month equal the API |
| 11 | `p9-11-money-overview.png` | Money | R | Net worth on screen equals the API (₹29,76,808) |
| 12 | `p9-12-accounts.png` | Accounts | R | Each bank balance equals the API (HDFC ₹1,86,400; SBI ₹2,42,000) |
| 13 | `p9-13-transactions-search.png` | Transactions | A | Server-side search for "Haldiram" |
| 14 | `p9-14-transaction-drawer.png` | Transactions | R | Detail drawer: source, category and how it was decided |
| 15 | `p9-15-spending.png` | Spending | I | Where money goes, by category |
| 16 | `p9-16-investments.png` | Investments | R | Current value equals the API (₹12,76,330) |
| 17 | `p9-17-debts-payoff.png` | Debts | R | Payoff planner; 35 months to debt-free equals the API |
| 18 | `p9-18-cash-flow.png` | Cash flow | R | Forecast ₹70,044 with range ₹36,260 – ₹1,03,827 beside the 3-month average, all equal to the API |
| 19 | `p9-19-retirement.png` | Retirement | I | FIRE projection from the person's own data |
| 20 | `p9-20-what-if-initial.png` | What-if | I | Two-step guided purchase form |
| 21 | `p9-21-what-if-validation.png` | What-if | E | Empty price blocked by the form ("Please fill in this field") |
| 22 | `p9-22-what-if-result.png` | What-if | R | Verdict from fixed rules after POST /decision (full page) |
| 23 | `p9-23-models-overview.png` | Risk & Models | R | All six capabilities with algorithm names (XGBoost, K-Means, TF-IDF, Isolation Forest, Model Lab) (full page) |
| 24 | `p9-24-credit-risk.png` | Credit Risk | R | 7.5% probability equals the API; SHAP factors |
| 25 | `p9-25-how-it-works.png` | Credit Risk | A | "How it works" explainer drawer |
| 26 | `p9-26-peers.png` | Peer Benchmarking | R | Peer group and percentiles |
| 27 | `p9-27-categoriser.png` | Categoriser | R | Suggested categories and try-it |
| 28 | `p9-28-unusual.png` | Anomaly Scanner | R | 4 flagged transactions (equals the API), each with reasons |
| 29 | `p9-29-model-lab.png` | Model Lab | R | Versions, datasets, metrics, acceptance checks (full page) |
| 30 | `p9-30-ask-initial.png` | AI CFO | I | Ask page with suggestions |
| 31 | `p9-31-ask-answer.png` | AI CFO | R | Live qwen2.5:3b answer stating the API net worth, "Figures checked" |
| 32 | `p9-32-ask-no-picks.png` | AI CFO | R | Request for fund picks: fixed reply, no named funds (Phase 9 guard) |
| 33 | `p9-33-import-initial.png` | Import | I | Four-step import |
| 34 | `p9-34-import-error.png` | Import | E | A non-statement CSV is refused with the reason ("Could not find a header row…") |
| 35 | `p9-35-import-preview.png` | Import | R | Synthetic sample: detected layout and preview |
| 36 | `p9-36-review.png` | Review | I | Review and corrections queue |
| 37 | `p9-37-records.png` | Records | I | Manual records by type |
| 38 | `p9-38-reports.png` | Reports | R | PDF generated (GET report.pdf 200); CSV and zip exports |
| 39 | `p9-39-profile-privacy.png` | Profile & privacy | I | What is stored, export, reset and delete |
| 40 | `p9-40-settings.png` | Settings | I | Account, security activity, profiles |
| 41 | `p9-41-signed-out.png` | Logout | R | Sign-out returns to sign-in; protected pages redirect |
| 42 | `p9-42-second-account-start.png` | Isolation | R | A second account starts empty; the first account's private profile returns 404 to it |
| 43 | `p9-43-debt-never-paid-off.png` | Debts | E | Loan with ₹2,000 EMI on ₹3,00,000 at 14%: "never paid off" and "Never cleared at this EMI" instead of "600 months" (Phase 9 fix) |
| 44 | `p9-44-debt-with-extra-payment.png` | Debts | R | With ₹10,000 extra a month, a real debt-free month count appears |

## Phase 8 design screenshots (responsive)

| Viewport | Files |
|---|---|
| Desktop 1440 | `01-sign-in-desktop`, `02-start-desktop`, `03-home-empty-private` (private profile with no data: guidance, no invented figures), `desktop-home`, `desktop-plan`, `desktop-plan-actions`, `desktop-plan-goals`, `desktop-plan-health`, `desktop-money`, `desktop-money-accounts`, `desktop-money-transactions`, `desktop-transaction-drawer`, `desktop-spending`, `desktop-money-investments`, `desktop-future`, `desktop-future-cashflow`, `desktop-future-retirement`, `desktop-future-whatif`, `desktop-models`, `desktop-models-credit-risk`, `desktop-models-peers`, `desktop-models-categoriser`, `desktop-models-unusual`, `desktop-model-how-it-works`, `desktop-lab`, `desktop-ask`, `desktop-data`, `desktop-data-import`, `desktop-data-profile`, `desktop-settings` |
| Tablet 768 | `tablet-home` (icon-rail navigation) |
| Mobile 390 | `mobile-home`, `mobile-navigation` (drawer menu), `mobile-plan`, `mobile-money`, `mobile-future-retirement`, `mobile-models`, `mobile-ask`, `mobile-data-import` |

## Not captured
- Tablet and mobile screenshots of the Phase 9 fixes. Their layouts are covered by the 55/55 responsive suite, but not re-photographed.
- An overdue goal ("target date passed"). The API refuses past target dates, so this state only appears as time passes. It is verified by `test_goal_progress_reached_and_overdue`, not by a screenshot.

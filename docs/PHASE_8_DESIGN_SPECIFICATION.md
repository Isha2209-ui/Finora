# Phase 8 design specification: Finora UI/UX redesign

**Status:** blueprint for owner approval. **Implementation has not started, and stage 8.6 may begin only after the owner approves this document.** Branch: `phase-8-ui-redesign`, created from `master` @ 21f0335. This repository's integration branch is `master`; there is no `main`.
**Readers:** the product owner (approval) and the implementer.
**Inputs:**
- [PHASE_8_DESIGN_CRITIQUE.md](PHASE_8_DESIGN_CRITIQUE.md) (`/design:design-critique`);
- [PHASE_8_WEB_GUIDELINES.md](PHASE_8_WEB_GUIDELINES.md) (`/web-design-guidelines`);
- [PHASE_8_THEME.md](PHASE_8_THEME.md) (`/theme-factory`);
- the owner's master prompt.

This document was written with `/doc-coauthoring`.

## 1. Goal and non-goals

**Goal:** turn Finora from a dark, 21-page module dashboard into a **guided, bright, calm financial workspace**:
- Apple-inspired visual refinement plus Stripe-inspired usability;
- every existing feature preserved and reachable;
- every figure shown once, where the task needs it.

**Non-goals:**
- no change to the Phase 7 AI engine, the Phase 6 models, financial calculations, authentication or profile isolation;
- no new features beyond the UI needed to expose existing ones;
- no new backend contracts unless §9 lists them and the owner approves them.

## 2. Critique findings that drive the design (summary)

1. **Navigation by module, not task:** 21 sidebar items in 5 groups, and 8 under "Intelligence" alone.
2. **The same figures on many pages:** net worth, surplus, runway and health on 4 pages; "4 unusual transactions" on 5.
3. **Overloaded pages:**
   - Statement Intelligence: 110 ₹ figures and 13 charts;
   - Model Lab: 4,581 px;
   - AI CFO: 11,826 px, because the chat history renders inline.
4. **No responsive shell:** the main column is 135 px wide at 375 px.
5. **Accessibility:** the faint text colour fails contrast (3.1–3.6:1); there are 54 uses of 10–11 px text, 6 ARIA attributes in total, `outline-none` on inputs, and `window.confirm` for destructive actions.
6. **Strengths to keep:** the Plan's evidence-first narrative, honesty labels, real data everywhere, and the Phase 7 streaming chat states.

## 3. Design direction

- **Visual:** the Finora Daylight theme (white and off-white, charcoal text, steel-blue accent `#3157c8`, semantic green, amber and red only for status, minimal shadows). Charts use the 5-colour chart palette plus "Other" and a dashed baseline (PHASE_8_THEME.md §2). Gradients appear in exactly two places:
  - the Home greeting band (`#f3f6fe` → white);
  - Ask: a 1 px gradient top border on the conversation area, and the send button (`#3157c8` → `#6e52d9`).
- **Usability:**
  - six task areas with URL-synced tabs;
  - summary first, details in drawers;
  - Stripe-style tables;
  - one trust component for every model output;
  - one conversation component for Ask.
- **Rule of three:** at most 3 headline figures and 1 chart above the fold on any screen. "Above the fold" means the first 900 px at 1440×900 and the first 812 px at 375×812. A headline figure is a figure rendered at `title` size or larger.

## 4. Information architecture

### 4.1 Areas and tabs (final, after auditing all 24 routes)

The 24 routes audited: 21 sidebar pages, `/models/review`, the start/lookup screen and sign-in.

| Area | Route | Tabs (`?tab=`) | Built from (current page → new home) |
|---|---|---|---|
| **Home** | `/` (signed in, profile chosen) | — | Plan headline and top findings (`Plan.jsx`) |
| **Plan** | `/plan` | Priorities · Actions · Your plan · Health · Goals · Tax | Plan findings, actions and scenario; **Recommendations** → Actions; Health score and pillars (from Identity); Goals (records); Tax regime (from Budget) |
| **Money** | `/money` | Overview · Accounts · Transactions · Spending · Investments · Debts | Identity (net worth, own/owe, liquidity, allocation) → Overview; **Accounts & Cards**; **Transaction Intelligence**; **Statement Intelligence** and the Budget part of Budget → Spending; **Investments**; payoff part of **Credit & Debt** → Debts |
| **Future** | `/future` | Cash flow · Retirement · What if · Savings | **Cash-Flow Forecast**; **FIRE & Retirement**; **Decision Simulator** and plan what-ifs; savings projections from Budget |
| **Risk & Models** | `/models` | Overview · Credit risk · Peers · Categoriser · Unusual activity · Model Lab | the six Phase 6 features (§4.3); **Model Lab** and `/models/review` |
| **Ask** | `/ask` | — | **AI CFO** page; the ChatPanel stays as a slide-over on every page |
| **Data** | `/data` | Import · Review · Records · Reports · Profile & privacy | **Import Statements**; **Review & Corrections**; **My Data**; **Reports**; **Profile & Data** |
| Settings | `/settings` (account menu) | Account · Security · Profiles | `/auth/me`, `/auth/activity`, sign out, switch, edit or delete profile |
| Start | `/start` (no profile chosen) | — | **Lookup** (demo picker, private profile creation) |
| Sign in | `/signin` | — | **SignIn** |

**Old routes redirect** to one target each, so bookmarks and docs keep working. A page that was split redirects to the part that matches its page title. The other part is linked from the target.

| Old route | Redirect target |
|---|---|
| `/identity` | `/money?tab=overview` (the health score moved to `/plan?tab=health`, linked there) |
| `/insights` | `/money?tab=spending` |
| `/budget` | `/money?tab=spending&view=budget` (tax is at `/plan?tab=tax`; savings at `/future?tab=savings`) |
| `/credit` | `/models?tab=credit-risk` (payoff strategies are at `/money?tab=debts`, linked there) |
| `/forecast` | `/future?tab=cash-flow` |
| `/fire` | `/future?tab=retirement` |
| `/decision` | `/future?tab=what-if` |
| `/cfo` | `/ask` |
| `/recommendations` | `/plan?tab=actions` |
| `/statements` | `/data?tab=import` |
| `/review` | `/data?tab=review` |
| `/records` | `/data?tab=records` |
| `/reports` | `/data?tab=reports` |
| `/accounts` | `/money?tab=accounts` |
| `/investments` | `/money?tab=investments` |
| `/transactions` | `/money?tab=transactions` |
| `/scanner` | `/models?tab=unusual` |
| `/peers` | `/models?tab=peers` |
| `/models/review` | stays (Model Lab → Review sub-page) |
| `/data` (old Profile & Data) | `/data?tab=profile` |

`/categorise` is an **API** endpoint, used by Risk & Models → Categoriser's "Try it on a narration"; it is not a page.

### 4.2 One home per figure

| Figure | Canonical home | Elsewhere |
|---|---|---|
| Net worth | Money → Overview | Home shows it in the one-line status only |
| Monthly surplus and savings rate | Money → Spending (summary) | Home status line |
| Runway / emergency fund | Plan → Health | — |
| Health score and pillars | Plan → Health | A header chip linking there |

"One home" means the full figure, with its breakdown and explanation, is rendered in exactly one place. Elsewhere it may appear only as a compact link: the Home status sentence, the header chip, or a badge count. Money → Overview's liquidity tiers show how reachable assets are; runway (months of expenses) stays in Plan → Health.
| Unusual transactions | Risk & Models → Unusual activity | Count badges linking there (Home priorities, Transactions filter) |
| Credit risk | Risk & Models → Credit risk | — |
| Forecast | Future → Cash flow | Risk & Models → Overview card (status plus link) |

### 4.3 The six Phase 6 features (all visible, all labelled)

| Feature | Home | Interface |
|---|---|---|
| Credit Risk | Risk & Models → Credit risk | Result, why (SHAP drivers), Taiwan 2005 scope, and "Try the model" (the score-a-card-history form) in a drawer |
| Peer Benchmarking | Risk & Models → Peers | You vs your group on 4 measures; US SCF 2022 and household caveat |
| Transaction Categoriser | Risk & Models → Categoriser | Pending suggestions queue (accept/reject), "Try it on a narration" (`/categorise`), suggestion-only status |
| Anomaly Detection Scanner | Risk & Models → Unusual activity | Flag list, detail drawer with reason, the not-fraud and experimental labels, link to the blinded review |
| Cash-Flow Forecast | Future → Cash flow; card in Risk & Models → Overview | One chart (actuals, forecast band, dashed baseline), a plain sentence, measured error |
| Model Lab and provenance | Risk & Models → Model Lab | One row per model (status, verdict, data); expand for metrics, criteria and provenance; Review sub-page |

## 5. Navigation architecture

- **Shell** (§4 of the guidelines):
  - ≥1280 px: labelled sidebar;
  - 768–1279 px: icon rail;
  - <768 px: top bar and drawer.
- **Sidebar:** Home, Plan, Money, Future, Risk & Models, Ask, Data (7 items), with only actionable badge counts:
  - findings to review on Plan: count of non-info items in `analysis.alerts`, as today's Recommendations badge;
  - transactions to review on Data: the review queue count from the existing review endpoint;
  - pending category suggestions on Risk & Models: from the analysis `category_suggestions`.

  The same counts appear on the matching tab.
- **Header:** profile name and demo chip, health chip (→ Plan → Health), an **Ask** button (opens the panel), and the account menu (Settings, Switch profile, Sign out).
- **Tabs:** in-page, underline style, URL-synced; the Back button restores the previous tab and filters.
- **"Ask about this":** on findings, actions, model results and table rows. It opens Ask with a pre-filled question (for example "Why is Haldiram's ₹18,293 on 31 Aug flagged?"). The Phase 7 planner then resolves it as usual; nothing is sent automatically.

## 6. Key user journeys

1. **First visit:** sign in, then Start (explore a demo person / start with my data), then Home.
2. **"Where do I stand?":** Home shows a one-line status and the top 3 priorities. Plan → Priorities shows the evidence; Actions has accept/dismiss; Your plan shows the impact.
3. **"Where does my money go?":** Money → Spending, with a segmented control (`?view=`) whose segments map to today's Statement Intelligence sections: Where it goes ("Where your money goes"), What changed ("What changed"), What repeats (recurring commitments), Who I pay ("Largest merchants"), Income (income sources), and Budget (from the Budget page). Picking a category opens Transactions, filtered.
4. **"Check something odd":** a Home priority or Transactions filter leads to Risk & Models → Unusual activity, then the detail drawer, with "Ask about this" available.
5. **"Import my statement":** Data → Import (Upload → Detect → Review → Done), then the Review queue, then Money updated (with a toast and an undo where supported).
6. **"Ask anything":** Ask, or the header panel, with streaming answers, interpretation, sources and Stop.
7. **"Can I afford / what if?":** Future → What if (Decision simulator) or Plan → Your plan (scenario engine).
8. **"How trustworthy is this?":** any trust chip leads to "How this was measured", which opens Model Lab at that model.

## 7. Page-by-page redesign

Each page lists its layout, followed by what is **preserved** (all of it must still work).

- **Home (`/`)**
  - **Layout:** greeting band with a tint gradient and the line "Aarav, here is where you stand." Below it, **one** status sentence built from real figures ("You keep ₹61,998 a month (47%) and have 13 months of runway."). Then the **top 3 priorities** as rows (title, why, one action button, "Ask about this"), and **4 entry tiles**: Review spending, Import a statement, Ask Finora, See your plan. Disclaimers go in the footer. No charts.
  - **Preserved:** Plan's narrative and data source (`GET …/plan`).
- **Plan**
  - **Priorities:** the findings list; each finding opens a drawer with evidence, why it matters, source, how sure, and Ask.
  - **Actions:** the ranked actions merged with Recommendations, with accept/dismiss and "Accepting only stores an assumption".
  - **Your plan:** the scenario engine (baseline vs plan).
  - **Health:** score, pillars and thresholds.
  - **Goals:** from records (add or edit in a drawer).
  - **Tax:** regime comparison.
  - **Preserved:** evidence, source, "how sure", accept/dismiss, the nothing-is-changed note, scenario inputs.
- **Money**
  - **Overview:** net worth with a 12-month trend (one chart), "What you own" and "What you owe" lists, liquidity tiers, allocation vs the age guide (one sentence plus a bar).
  - **Accounts:** a table of bank accounts and cards; a row opens a drawer with the balance source, as-of date, utilisation and Edit (the records form).
  - **Transactions:** Stripe table (search, chips for account, category, period, "Unusual only" and "Suggested category"); a row opens a drawer with category accept/reject, the anomaly explanation, Delete (confirm modal) and Ask; plus CSV export.
  - **Spending:** the segmented questions (journey 3), each with at most 1 chart plus a ranked list; budget limits included.
  - **Investments:** holdings table plus allocation; SIP summary.
  - **Debts:** loans and cards with payoff strategies (avalanche/snowball).
  - **Preserved:** all record editing (via drawers), period and account filters, cleaning rules, CSV export.
- **Future**
  - **Cash flow:** forecast sentence, one chart, measured error vs baseline, trust chip.
  - **Retirement:** FIRE inputs (left) and projection (right).
  - **What if:** the decision simulator.
  - **Savings:** savings projection.
  - **Preserved:** all inputs, assumptions, the baseline and the honesty copy.
- **Risk & Models**
  - **Overview:** 6 rows, one per feature: name, what it does, status chip, one-line result, Open.
  - **Other tabs:** as in §4.3.
  - **Preserved:** every metric, criterion, provenance item, the blinded review, and both experimental labels.
- **Ask** (§8)
- **Data**
  - **Import:** stepper with real progress.
  - **Review:** the queue.
  - **Records:** the full editor for every record type (power-user view; Money drawers reuse its forms).
  - **Reports:** PDF and zip/CSV export.
  - **Profile & privacy:** data summary, delete profile, sandbox reset (modal).
- **Settings**
  - **Account:** e-mail and display name, **read-only** (no account-edit endpoint exists).
  - **Security:** recent activity from `/auth/activity`, plus sign out.
  - **Profiles:** switch, edit details, delete.
  - **Not offered:** password change and preferences have no backend; see §12.
- **Start / Sign in:** a light split layout; demo picker and private-profile creation; preserves the PAN-never-fetches-data copy and sandbox semantics.

## 8. AI CFO (Ask)

- **Layout:**
  - **Left (main):** a scrolling conversation in its own scroll container (fixing the 11,826 px page) and a composer anchored at the bottom.
  - **Right rail:** suggested questions (built from the user's actual priorities), the monthly briefing, and "How answers are checked" (the 4 steps).
- **Preserved Phase 7 states:**
  - the stage text (Understanding → Fetching your data → Writing → Correcting the draft);
  - "Understood as …";
  - tool and source chips;
  - the draft labelled "Draft, being checked";
  - the verified badge; Stop (Esc);
  - "Stopped. Nothing from this answer was saved.";
  - the local-model notice when offline;
  - general vs personal labelling.
- **Accessibility:** the answer region has `aria-live="polite"`; Enter sends, Shift+Enter adds a newline.
- **Panel mode:** the same component at 420 px, opened from the header or from "Ask about this".
- **Charts in answers:** no new backend work. The Phase 7 stream's `final` event already carries the plan's `steps` and their results. A small chart is shown only for steps whose results contain a series: a comparison of two periods (two bars), or a list of individual transactions (a ranked bar list). Otherwise there is no chart.

## 9. Backend integration

- **No API contract changes are planned.**
- **Endpoints used:**
  - `/auth/*`;
  - `/profiles/*` (analysis, plan, records, transactions, upload, statements, review, chat, chat/stream, briefing, reports, export);
  - `/models/lab`, `/models/metrics`, `/models/credit-risk/score`, `/categorise`.
- **Data loading** stays on the cached analysis (`store.jsx`); tabs fetch lazily only where their page does today.
- **Possible additions (owner decision, §12):** a change-password endpoint, and saved UI preferences.

## 10. Components to build (in `frontend/src/components/`)

1. `AppShell` (rail, drawer, header, account menu, skip link);
2. `PageHeader` with `Tabs` (URL-synced);
3. `Button` (4 variants);
4. `Input`, `Select`, `Field` (labels, hints, errors);
5. `DataTable` (toolbar, chips, search, pagination, row → drawer, states);
6. `Drawer`;
7. `ConfirmModal` (replaces every `window.confirm`);
8. `Toast` (with Undo);
9. `Stat` (rule of three);
10. `TrustChip` / `TrustNote` (status, limitation, "How this was measured");
11. `ChartFrame` (title as a question, one-sentence summary, "View as table", theme colours);
12. `EmptyState`, `Skeleton`, `ErrorState`;
13. `Conversation` (Ask page and panel);
14. `AskAboutThis` link.

All of them use the theme tokens only; hard-coded colours are not allowed.

## 11. Interaction, accessibility and testing requirements

- **Interaction:** per guidelines §§11–16: 150–200 ms opacity/transform transitions, toasts for saves, drawers for detail, modals only for confirmation, and keyboard shortcuts (`/` for search, Esc to close or stop).
- **Accessibility:** WCAG 2.2 AA per guidelines §6:
  - contrast verified by theme tokens;
  - visible focus;
  - landmarks and a skip link;
  - ARIA names on icon buttons;
  - live regions;
  - 44 px touch targets;
  - charts with a text summary and a table view.
- **Testing:** `/playwright` CLI against the running app at every stage (8.6–8.15):
  - sign in / register / sign out;
  - every nav item and tab, plus the old-route redirects;
  - forms (records add/edit, credit-risk scoring, decision simulator) including validation;
  - filters and search on Transactions;
  - statement import end to end with the sample CSV;
  - AI CFO streaming, Stop, history reload and "Ask about this" pre-fill;
  - modals and drawers (open, Esc, focus return);
  - responsive at 375, 768, 1280 and 1440;
  - empty states (the empty private profile) and error states (API down);
  - no console errors;
  - an axe-style check where available.

  The existing 484 backend tests must keep passing (the backend is unchanged).

## 12. Open decisions for the owner

1. **Approve the IA in §4.1.** Notably: Recommendations merges into Plan → Actions; Budget is split across Money → Spending, Plan → Tax and Future → Savings; Credit & Debt is split into Money → Debts and Risk & Models → Credit risk.
2. **Password change and preferences.** Either add a small backend endpoint in Phase 8 (an exception to "frontend only"), or show Settings without them. **Recommendation:** without them; listed as a known gap.
3. **Theme.** Approve Finora Daylight (PHASE_8_THEME.md). There will be no dark mode in Phase 8; the dark theme is retired. **Recommendation:** light only, dark as a later option.

## 13. Implementation plan (after approval)

| Stage | Work | Skill(s) | Done when |
|---|---|---|---|
| 8.1–8.5 | Critique, guidelines, theme, spec | design-critique, web-design-guidelines, theme-factory, doc-coauthoring | **Done** (this document) |
| 8.6 | Tokens in `index.css`, `AppShell`, nav, routes and redirects, components 1–8 | web-design-guidelines | Every old route resolves; the shell passes at 375–1440; Playwright smoke passes |
| 8.7 | Home and Plan | theme-factory and playwright | Journeys 1–2 pass |
| 8.8 | Money (tabs and drawers, DataTable) | web-design-guidelines and playwright | Journeys 3 and 5 (Money side); records editing via drawers |
| 8.9 | Ask (`Conversation`) | playwright | Streaming, Stop, history and Ask-about-this pass |
| 8.10 | Future | playwright | All inputs and charts real; journey 7 |
| 8.11 | Risk & Models | playwright | All six features usable; journey 8 |
| 8.12 | Data and Settings | playwright | Journey 5 end to end; destructive actions use ConfirmModal |
| 8.13 | Responsive and accessibility pass | web-design-guidelines and playwright | Guidelines §6 checklist met |
| 8.14 | Final design critique | design-critique | Re-measured density table; no 🔴 findings |
| 8.15 | Docs and verification | doc-coauthoring and playwright | PHASE_8_VERIFICATION.md with real results |

**Gating:** 8.6 starts only after owner approval. Each later stage starts only when the previous stage's "Done when" holds; for example, Money (8.8) needs the 8.6 shell and components and the 8.7 journeys passing.

**Order rationale:** shell and components first, so every later page reuses them. Home and Plan next, because they are the demo path.

## 14. Acceptance criteria (from the owner's prompt, made testable)

1. The Finora Daylight tokens are the only colours in the code (a grep finds no hex outside `index.css` and the chart theme).
2. The primary surfaces are white or off-white.
3. Every screen has at most 3 headline figures and 1 chart above the fold (re-measured as in critique §2).
4. Navigation has ≤ 8 top-level items, and every old route redirects correctly (Playwright).
5. Journeys 1–8 pass in Playwright.
6. Every feature in the current app is reachable (the route map in §4.1 is checked one by one).
7. All six Phase 6 features are visible and functional, with trust chips.
8. Ask keeps every Phase 7 state (§8).
9. Every visible control performs a real action. **Procedure:** for each screen and tab, take a Playwright accessibility snapshot and list every button, link, tab, checkbox and select. Activate each one, then assert at least one of: a URL change, an API request (method and path recorded), or a visible state change (drawer or modal opens, list filters, value updates). Any control with no observable effect is a failure. Unsupported actions are absent, not decorative.
10. All figures come from API responses; no hard-coded financial values (code review plus grep).
11. There are no fake interactions or dummy charts.
12. There is no horizontal scroll at 375, 768, 1280 or 1440, and the shell adapts.
13. The accessibility checklist (guidelines §6) is met; contrast is verified.
14. Critical workflows pass Playwright, and the backend suite still passes.
15. The final design critique is completed with no 🔴 findings.
16. PHASE_8_VERIFICATION.md is written from real results.

## 15. Revisions made during implementation

These follow the mid-implementation design critique (see PHASE_8_DESIGN_CRITIQUE.md, second part).

1. **Answer-first composition.** It is used on Accounts, Investments, Cash flow, Retirement, What if, Peers, Unusual activity, Goals and Profile & privacy:
   - one plain-language sentence answers the screen's question (`Answer`);
   - 2–3 supporting facts follow in a quiet row (`Facts`), not stat cards;
   - then lists (`List`/`Row`) whose rows open detail drawers;
   - methods and long caveats sit behind `<details>` disclosure.
2. **One header per screen.** Inside an area, a page's own title becomes a visually hidden `h2`; the tab names it, and only its one-line lead and actions show.
3. **Moves.**
   - "Add a transaction" moves from Profile & Data to Money → Transactions (button and drawer).
   - Profile details are edited only in Settings → Profiles.
   - Data → Profile & privacy keeps what is stored, export, demo reset and a delete danger zone.
4. **Import** shows a visible four-step guide: Choose a file → Check what Finora found → Import → Review and finish.
5. **Backend (allowed by §9).** `GET /profiles/{id}/transactions` gains optional `sort` and `suggested_only`. The defaults are unchanged and a new test covers them.
6. **Not built: charts inside AI answers (§8).** The stream's final event does not include tool results (Phase 7 strips `facts`), so a chart would need a backend change. This is recorded as a known gap.

## 16. Presentation revision (owner decision, final round)

1. **Model identity replaces status labels.**
   - The trust component (`Trust`) shows **"Model: {algorithm}"** and a **How it works** drawer. The drawer gives purpose, inputs, method, explanation, how to read the result and the data source, plus a link to Model Lab's technical details.
   - Status labels (accepted / experimental / acceptance criteria) are no longer displayed. Status, metrics, evaluation checks, versions and provenance are unchanged in the backend and in Model Lab's expandable sections, under neutral headings.
   - The single source for model descriptions is `frontend/src/components/models.js`, written from the implementations in `backend/app/ml`.
2. **No academic or advisory disclaimers.** They are removed from every screen and from AI CFO answers (`writer.DISCLAIMER` is now empty). Older saved answers are cleaned on display. The prompts no longer ask for disclaimers. "Do not recommend specific stocks or funds" stays as a behaviour rule. Factual product statements stay: the demo-copy indicator, data provenance and "unusual compared with your own history".
3. **Registration.**
   - No per-IP sign-up limit by default (`REGISTER_IP_MAX=0`); a public deployment can set it.
   - Sign-in's per-IP cap counts only failed attempts.
   - Unique e-mails, hashing, password rules, per-e-mail lockout, sessions and isolation are unchanged.
4. **Goals.** A progress view with both monthly figures (7% assumed growth, or none) and a short explanation of the assumption; the editor sits below.

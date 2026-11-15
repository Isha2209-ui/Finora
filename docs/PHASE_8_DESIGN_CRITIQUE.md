# Phase 8 design critique: Finora as it stands (2026-11-15)

**Method.** `/design:design-critique` framework: first impression, usability, visual hierarchy, consistency and accessibility, followed by priority recommendations. It was applied to the running app (`master` @ 21f0335, demo sandbox of Aarav Mehta, 1440×900) using:
- the DOM and page text of all 21 sidebar routes plus `/models/review`, `/` (lookup) and sign-in;
- measured density per page (table below);
- computed WCAG contrast of the current colour tokens;
- a 375 px viewport check;
- a read of `Layout.jsx`, `ui.jsx`, `index.css` and every page component.

**Stage.** Pre-redesign audit. **Approved direction:** Apple-inspired visual refinement plus Stripe-inspired usability, with a bright white primary theme.

**Caveat.** Screenshots from the hidden browser pane rendered the main column dimmed. That was verified to be a capture artifact (computed colour `#e6edf7`, opacity 1, no overlay), so it is not reported as a defect.

## Overall impression

Finora's substance is strong: real figures, honest model labelling, evidence on every finding, and a guided Plan page. Its presentation works against it:
- **A dark "terminal" theme.** It suggests a trading tool, not a calm personal product.
- **A 21-item sidebar.** It is organised by technical module (Overview / Intelligence / Planning / System) rather than by what a person wants to do.
- **The same headline numbers repeated on most pages.**

The biggest opportunity: **keep every feature and every number, but show each one once, in the place where the user's task needs it.**

## Measured density (main column, 1440×900)

| Page | Height (px) | ₹ figures | Charts | Cards | Notes |
|---|---|---|---|---|---|
| /plan | 1,294 | 5 | 0 | 3 | Already guided: the best page |
| /identity | 1,514 | 34 | 3 | 15 | Repeats Plan stats, plus every asset class |
| /insights | **2,616** | **110** | **13** | 13 | Heaviest page |
| /transactions | 2,218 | 45 | 1 | 7 | 30 inputs (filters plus per-row controls) |
| /budget | 1,960 | 49 | 9 | 11 | Budget, savings and tax on one page |
| /models | **4,581** | 0 | 5 | 7 | 1,447 words of provenance on one screen |
| /cfo | **11,826** | 69 | 0 | 76 | The whole chat history renders inline on the page |
| /recommendations | 1,664 | 20 | 0 | 10 | Overlaps Plan "What to do" |
| /fire | 1,458 | 31 | 1 | 10 | |
| /credit | 1,450 | 10 | 0 | 8 | 21 inputs (the "score a card history" form) |
| /investments | 1,446 | 45 | 2 | 9 | |
| /forecast | 1,336 | 13 | 5 | 11 | |
| /accounts, /scanner, /peers, /data, /records | 990–1,070 | 0–17 | 0–1 | 2–7 | Moderate |
| /statements, /review, /decision, /reports | 808 | 0–6 | 0 | 2–3 | Light |

## 1. First impression (2 seconds)

- **What draws the eye first:**
  - the teal-on-navy sidebar, which is the brightest, most saturated region;
  - the yellow demo banner;
  - the "Health 95.2/100" chip in the header.

  The user's actual subject (the Plan headline "Aarav, here is where you stand.") comes fourth. **Incorrect:** the content should win.
- **Emotional reaction:** technical, dense and serious. It is closer to a monitoring console than to the calm, premium product the owner described.
- **Purpose:** clear on /plan, which leads with one sentence plus four numbers plus findings. It is unclear everywhere else, because 20 other pages open with their own wall of figures.

## 2. Usability

| Finding | Severity | Recommendation |
|---|---|---|
| 21 sidebar items in 5 technical groups. "Intelligence" alone has 8 items, and labels mix task names ("Import Statements") with module names ("Transaction Intelligence", "Statement Intelligence") that users can't tell apart. | 🔴 Critical | Use 6 task-based areas (Plan, Money, Future, Risk & Models, Ask, Data) with second-level tabs inside each area. |
| **No responsive shell.** At 375 px the 240 px sidebar stays fixed and the main column is **135 px** wide; nothing collapses. | 🔴 Critical | Build a collapsible shell: an icon rail at ≤1024 px and a drawer plus top bar at ≤768 px. |
| The same figures appear on many pages: net worth / surplus / runway / health on Plan, Identity, Insights and the header chip; "4 unusual transactions" on Plan, Identity, Recommendations, Transactions and Scanner. | 🔴 Critical (information overload) | Give each figure one canonical home. Other places link to it ("4 to check →") instead of re-rendering it. |
| Overlapping pages: Plan "What to do" vs **Recommendations**; Accounts vs **My Data** vs **Profile & Data**; Insights vs Transactions vs Budget (all spending analysis). | 🟡 Moderate | Merge into one area each, with tabs. Recommendations becomes Plan → "All actions". |
| AI CFO page: the full conversation renders as one 11,826 px column, and the chat is also a slide-over panel on every page. Two entry points behave differently. | 🟡 Moderate | One conversation component: a full page for Ask, plus a compact panel with a scroll container and "Ask about this" deep links. |
| Long scientific pages (Model Lab is 4,581 px with 1,447 words) show method, metrics and provenance all at once. | 🟡 Moderate | Use progressive disclosure: status and one-line verdict per model, with "How it was measured" and "Provenance" expandable. |
| Tables carry per-row controls (Transactions has 30 inputs on one screen). | 🟡 Moderate | Stripe-style table: a filter bar above, a row click opens a detail drawer with the edit controls. |
| Header has 5 controls (refresh, Ask AI CFO, switch profile, account, sign-out) with icon-only buttons and no labels. | 🟢 Minor | Fewer, labelled controls. Move the profile switcher and account into one menu. |
| `/` for a signed-in user without a profile opens "Lookup"; `/models/review` exists but is not in the sidebar. | 🟢 Minor | Keep both, reachable from their parent area (Data → Profiles; Risk & Models → Model Lab → Review). |

## 3. Visual hierarchy

- **Reading flow:**
  1. sidebar;
  2. banner;
  3. header chip;
  4. page title;
  5. a row of 4–5 equally weighted stat cards;
  6. charts.

  Every stat card has the same size, colour and weight, so nothing says which number matters.
- **Emphasis:**
  - figures are emphasised everywhere (₹ in large type), so none stands out;
  - honesty labels ("experimental", "not fraud") are tiny grey 10–11 px text and easy to miss, although they are a core product value.
- **Whitespace:** cards sit tight in grids with `gap-4` inside a `px-6` column; there is no breathing room between sections.
- **Typography:**
  - one family (Inter);
  - sizes are ad hoc: 42 uses of `text-[11px]`, 15 of `text-[13px]`, plus 10, 10.5, 11.5, 15, 28 and 34 px;
  - no defined scale, so hierarchy depends on colour rather than size and weight.

## 4. Consistency

| Element | Issue | Recommendation |
|---|---|---|
| Colour | Dark tokens only (`--color-bg #070b14`). Teal accent used for links, active nav, buttons, charts and badges alike. | A light token set: white/off-white surfaces, charcoal ink, one restrained blue accent, semantic green/amber/red only for status. |
| Typography | 10+ arbitrary pixel sizes | A 7-step type scale with tokens; numbers stay `tabular-nums`. |
| Cards | Card, Stat and KV used with different paddings; some pages nest cards inside cards (Identity: liquidity inside a card inside a grid). | One surface style: no nested cards. Sections are separated by whitespace and headings, not borders. |
| Charts | recharts with dark-specific overrides in `index.css`; legend and colours vary per page (Insights shows 10 category colours at once). | A chart theme with tokens; at most 5 series, and the rest grouped as "Other". |
| Model honesty labels | Each page words them differently (Note, Badge, inline text). | One **trust component**: status chip (Accepted / Experimental / Suggestion only), one-line limitation, and "How this was measured" linking to Model Lab. |
| Buttons | Primary teal, ghost and inline text links mixed; some icon-only. | Three variants (primary, secondary, quiet) with labels; icon-only only with an `aria-label`. |

## 5. Accessibility

- **Colour contrast** (computed on the current tokens):
  - ink `#e6edf7` scores 14–17:1, a pass;
  - muted `#8695ad` scores 5.5–6.5:1, a pass;
  - **faint `#5b6a84` scores 3.1–3.6:1, a FAIL for normal text**. It is used for 10–11 px labels, provenance and the sidebar footer, exactly the small text that most needs contrast.
- **Text size:** 54 usages of 10–11 px text. Legal and honesty notes are the smallest text on screen.
- **Semantics and ARIA:**
  - only **6** `aria-` attributes in the whole frontend;
  - icon-only header buttons lack accessible names;
  - charts have no text alternative (the data is usually also in text nearby, which helps).
- **Keyboard:** native buttons and links are used (good); the default focus ring is barely visible on the dark theme.
- **Touch targets:** sidebar items are 30 px high and header icon buttons about 32 px, below the 44 px guideline on touch devices.
- **Motion:** `.rise` respects `prefers-reduced-motion` (good).

## 6. Page by page

For each page: **what exists**, **what's wrong**, **why it matters**, **what should change**, and **what must be preserved**.

**Sign-in / register**
- **Exists:** e-mail and password, a privacy note.
- **Wrong:** a dark, unbranded form.
- **Why:** it is the first impression of a premium product.
- **Change:** a light split layout with a short value statement.
- **Preserve:** argon2/httpOnly session copy and rate-limit errors.

**Lookup / start (`/` with no profile)**
- **Exists:** the demo identity picker plus "Build my financial identity".
- **Wrong:** it is not a "home"; it shows the two paths side by side with dense text.
- **Change:** a welcome step with two clear choices (Explore a demo person / Start with my own data).
- **Preserve:** the "PAN never fetches data" honesty copy, 24-hour sandbox semantics, private profile creation.

**Finora Plan (`/plan`)**
- **Exists:** a headline, 4 stats, three steps (What we found 6 / What to do 3 / Your plan), findings with evidence, source and certainty.
- **Wrong:** good structure, but the 4 stats compete with the headline, and findings are long text blocks.
- **Why:** the Plan should be the calm home.
- **Change:** make it **Home**: greeting, one-sentence status, the top 3 priorities as cards (problem, why, action, impact), "Ask about this" on each, then the rest progressively.
- **Preserve:** evidence, source, "how sure", accept and dismiss actions, the "Nothing is changed" note, the scenario engine (Your plan).

**Financial Identity (`/identity`)**
- **Exists:** 34 ₹ figures, 3 charts, health pillars, assets, liabilities, liquidity, allocation, priorities.
- **Wrong:** it duplicates Plan stats and Recommendations; it is a dashboard of everything.
- **Change:** split into **Money → Overview** (net worth trend, what you own and owe) and **Plan → Health** (score and pillars).
- **Preserve:** data-completeness banner, "—" for missing data, pillar thresholds, allocation guide note.

**My Data (`/records`)**
- **Exists:** an editor for every record type (19 buttons).
- **Wrong:** a separate page from Accounts and Investments, which show the same records read-only.
- **Change:** edit **in place**: each Money tab (Accounts, Cards, Loans, Investments) gets "Add" and "Edit" in a drawer, using the same forms. Keep the Data area for bulk management.
- **Preserve:** every record type, validation, and the immutable account uid used for undo.

**Import Statements (`/statements`) and Review & Corrections (`/review`)**
- **Exists:** CSV upload with layout detection, progress, a review queue.
- **Wrong:** split across two nav items and far from each other.
- **Change:** **Data → Import** as a stepper (Upload → Detect → Review → Done), with the review queue as its last step and a badge count in navigation.
- **Preserve:** large-import progress, rollback messaging, transfer, refund and income detection, undo.

**Accounts & Cards (`/accounts`) and Investments (`/investments`)**
- **Exists:** reasonable density.
- **Change:** become Money tabs with a table plus a detail drawer.
- **Preserve:** balance source and as-of dates, card utilisation, holdings with gains.

**Statement Intelligence (`/insights`)**
- **Exists:** 110 figures and 13 charts in one scroll: category breakdown, change over time, what changed, merchants, recurring, income.
- **Why it's wrong:** it overloads the user, and every chart has equal weight.
- **Change:** **Money → Spending** with one question per view:
  - "Where does my money go?" (one ranked bar list);
  - "What changed?" (top 3 movers);
  - "What repeats?" (recurring);
  - "Who do I pay most?" (merchants);
  - "Where does income come from?".

  Use a segmented control, not one scroll.
- **Preserve:** account and period filters, the same cleaning rules, refunds netted.

**Transaction Intelligence (`/transactions`)**
- **Exists:** a full table with 30 inputs, categories, anomaly scores, CSV export.
- **Change:** a Stripe-style table: search, a filter chips bar (account, category, period, "unusual only"), row click opens a drawer with category suggestion accept/reject and the anomaly explanation.
- **Preserve:** CSV export, categoriser suggestion-only semantics, the "Unusual for you ≠ fraud" note.

**Anomaly Scanner (`/scanner`) and Model review (`/models/review`)**
- **Exists:** flagged list, experimental warning, blinded review.
- **Change:** Risk & Models → **Unusual activity**, with the flag list, the trust component and "Review in Model Lab".
- **Preserve:** the experimental and not-human-validated label, and the blinded review workflow.

**Cash-Flow Forecast (`/forecast`)**
- **Exists:** prediction, range, baseline, 5 charts.
- **Change:** **Future → Next month**: one chart (actuals, forecast band and baseline line) plus a plain-language sentence. Provenance goes behind the trust component.
- **Preserve:** the baseline beside the model, "less accurate than the baseline" honesty, the range.

**Credit & Debt (`/credit`)**
- **Exists:** card default risk, utilisation, EMIs, payoff strategies, and the "score a card history" form (21 inputs).
- **Change:**
  - debts go to **Money → Debts** (payoff strategies);
  - credit risk goes to **Risk & Models → Credit risk**, with the scoring form in a separate "Try the model" panel.
- **Preserve:** the Taiwan 2005 benchmark scope, why-this-result explanation, avalanche and snowball.

**Peer Benchmarking (`/peers`)**
- **Exists:** a moderate page.
- **Change:** Risk & Models → Peers, with a "you vs group" comparison.
- **Preserve:** the US SCF 2022 and "household vs person" caveats.

**Budget, Savings & Tax (`/budget`)**
- **Exists:** 49 figures and 9 charts covering three different jobs.
- **Change:**
  - budget goes to **Money → Spending → Budget**;
  - savings goes to **Future → Savings**;
  - tax goes to **Plan → Tax**, since it is a decision.
- **Preserve:** the tax regime comparison and its numbers.

**FIRE & Retirement (`/fire`) and Decision Simulator (`/decision`)**
- **Change:** Future → Retirement and Future → What if.
- **Preserve:** inputs, assumptions and projections.

**AI CFO (`/cfo`) and ChatPanel**
- **Exists:** streaming, interpretation, tool badges, draft, Stop, explainer card, briefing, alerts.
- **Wrong:** history renders as an endless page; briefing, alerts and the explainer compete with the chat.
- **Change:** **Ask** as a two-pane layout: a scrolling conversation with an anchored composer, plus a side rail with suggested questions, briefing and "how answers are checked". "Ask about this" links from every area pre-fill a question.
- **Preserve (all of Phase 7):** streaming states, "Draft, being checked", interpretation line, tools used, verified badge, Stop, local-model notice.

**Recommendations (`/recommendations`)**
- **Change:** merge into Plan → "All actions"; the nav badge becomes a Plan badge.
- **Preserve:** accept and dismiss, alert levels.

**Reports (`/reports`)**
- **Change:** Data → Reports.
- **Preserve:** PDF generation.

**Model Lab (`/models`)**
- **Exists:** 4,581 px and 1,447 words.
- **Change:** one row per model: status chip, verdict, data source, and "Details" expanding the metrics, provenance and acceptance criteria.
- **Preserve:** every metric, unmet criteria, provenance and the experimental flags.

**Profile & Data (`/data`)**
- **Change:** **Data → Profile & privacy**: export, delete, sandbox reset. Account security goes to Settings.
- **Preserve:** destructive-action confirmations.

## 7. What works well (keep)

- **The Plan's narrative.** One sentence, then findings with evidence, source and "how sure". This is the model for the whole product.
- **Honesty is built in.** Synthetic vs real, experimental vs accepted, "unusual is not fraud", baselines beside models, US/Taiwan scope.
- **Tabular numerals** (`.num`), Indian ₹ / lakh formatting, and real data behind every figure.
- **Phase 7 chat states.** Streaming, the interpretation line, the draft label and Stop are already good interaction design.
- **Respect for `prefers-reduced-motion`**, native buttons and links, and a working print stylesheet.

## 8. Priority recommendations

1. **Restructure navigation around 6 tasks with second-level tabs**, and give every figure one canonical home. This removes most of the overload without removing a single feature.
2. **Replace the dark token set with the approved light system and a real type scale**, including the faint-text contrast fix. Calm comes mainly from colour, type and whitespace.
3. **A responsive, accessible shell:** collapsing navigation, 44 px targets, visible focus, ARIA names on icon buttons.
4. **Progressive disclosure as the default pattern:** a summary sentence, then a few figures, then a detail drawer or "How this was measured".
5. **One trust component and one conversation component**, reused everywhere, so model honesty and Ask look and behave the same on every page.

---

# Mid-implementation review (`/design:design-critique`, 2026-11-15)

An honest review of the redesign as first implemented. It is based on full-page screenshots of every area and tab at 1440×900. The owner's concern was correct: several tabs were the old page component on the new palette, placed inside a new tab.

## Classification

| Area / screen | Classification | Evidence |
|---|---|---|
| Sign in / register | **Genuine UX redesign** | New split layout, inline validation, show-password, honest recovery note |
| Start (first run) | **Genuine UX redesign** | Two-path guided choice, returning profiles first |
| Shell and navigation | **Genuine UX redesign** | 7 task areas, URL tabs, responsive rail/drawer, account menu, skip link |
| Home | **Genuine UX redesign** | One status sentence, 3 priorities, next steps; no dashboard |
| Ask | **Layout restructuring** | Two-pane, own scroll, rail; message design new; engine unchanged |
| Settings | **Genuine UX redesign** (new) | Account / Security / Profiles, honest "unavailable" list |
| Plan → Priorities / Actions / Your plan | **Mostly visual restyling** | Phase 5's guided flow kept as-is: good, but pill buttons and boxes are the old style |
| Plan → Health, Tax | **Layout restructuring** | Split out of Identity/Budget, pillar meters replace radar |
| Plan → Goals | **Mostly visual restyling** | Records editor in a drawer |
| Money → Overview | **Layout restructuring** | Net-worth hero, one chart, own/owe |
| Money → Accounts | **Mostly visual restyling** | Old 4-card stat strip + old tables |
| Money → Transactions | **Genuine UX redesign** | Stripe table, URL filters, sort, detail drawer |
| Money → Spending | **Layout restructuring** | Question-led segmented views |
| Money → Investments | **Mostly visual restyling** | Old stats + tables |
| Money → Debts | **Layout restructuring** (light) | |
| Future → Cash flow | **Mostly visual restyling** | Stats reduced to 3, otherwise the old page |
| Future → Retirement | **Mostly visual restyling** | 5 equal stat cards; the answer is not stated |
| Future → What if | **Mostly visual restyling** | Old form + result |
| Future → Savings | **Layout restructuring** | |
| Risk & Models → Overview, Categoriser | **Genuine UX redesign** (new) | |
| Risk & Models → Credit risk | **Layout restructuring** | Trust chip, labelled form |
| Risk & Models → Peers | **Mostly visual restyling** | "Model version" shown as a headline stat; two notes |
| Risk & Models → Unusual activity | **Mostly visual restyling** | Two stacked warnings, 4 stat cards incl. model version |
| Risk & Models → Model Lab | **Layout restructuring** | Progressive disclosure per model |
| Data → Import | **Mostly visual restyling** | No visible step structure |
| Data → Review, Reports | **Mostly visual restyling** | |
| Data → Records | **Layout restructuring** | Drawer editing, URL type |
| Data → Profile & privacy | **Mostly visual restyling, and duplicative** | Repeats Import, Records and profile editing |

## Systemic findings

| Finding | Severity | Recommendation |
|---|---|---|
| Every tab shows two stacked headers (area title + subtitle, then the page's own title + subtitle). "Money / Accounts & Cards" says the same thing twice and pushes content below the fold. | 🔴 | Inside an area, a page shows only its one-line lead and actions. The tab already names it. |
| Rows of 4–5 equal stat cards remain on Accounts, Investments, Retirement, Unusual activity and Peers. Nothing says which number matters. | 🔴 | An **answer-first** pattern: one plain-language sentence that answers the page's question, 2–3 supporting facts in a quiet inline row (not cards), then the detail. |
| Model internals (version strings, tree counts) are presented as headline statistics. | 🟡 | Move them into the trust chip and Model Lab. Headlines are about the user. |
| Stacked warning boxes (Unusual activity has two, Peers one long one). | 🟡 | One trust line (status + limitation + link), with the long explanation behind disclosure. |
| Import has no visible steps; Profile & privacy duplicates other screens. | 🔴 | Visible 4-step import; Profile & privacy limited to what is stored, export, delete, reset. Adding a transaction moves to Money → Transactions. |

## Priority recommendations
1. **Answer-first composition** on Accounts, Investments, Cash flow, Retirement, What if, Peers and Unusual activity: rebuild the page composition, not the CSS.
2. **Single header per screen** inside areas.
3. **Guided Import** and a focused **Profile & privacy**; "Add transaction" where transactions live.
4. **Plan steps** on the shared button and surface system.

---

# Final post-implementation critique (`/design:design-critique`)

The whole application was reviewed from 39 screenshots (desktop, tablet and mobile) and the live app.

**Overall impression.** A calm, white, answer-first product. Each screen opens with one sentence that answers its question, and detail is one click away. No screen still reads as the old dark dashboard. The six ML features are identified by name and algorithm, with plain explanations.

| Finding | Severity | Resolution |
|---|---|---|
| Drawers opened inside the tab panel (clipped, below the header), because the panel's entrance animation kept a containing block for `position: fixed` | 🔴 | **Fixed:** drawers and modals render through a portal to `<body>`; verified by screenshot and the 43/43 functional run |
| Home sentence read "your financial health is needs attention" | 🟡 | **Fixed:** the sentence adapts to the band |
| Mobile header Ask button had no accessible name | 🟡 | **Fixed:** `aria-label="Ask Finora"`; responsive suite 55/55 |
| Duplicate HTML id (`ask-panel`) between the panel and its input | 🟡 | **Fixed** |
| Plan → Priorities / Actions / Your plan, Data → Review, `/models/review` remain light restyles of working flows | 🟢 | Accepted: guided and functional; listed in the verification report |

**What works well.**
- Answer-first composition is consistent across Money, Future and Risk & Models.
- Model identity chips and "How it works" drawers explain the ML clearly.
- Transactions is a clean, fully functional table.
- Navigation is responsive (sidebar, rail, drawer), with a skip link, focus rings and live regions.

# Phase 8 web design and UX guidelines (Finora)

**Source.** Produced with `/web-design-guidelines`, which fetched the latest Vercel Web Interface Guidelines (`vercel-labs/web-interface-guidelines/command.md`) on 2026-11-15 and checked them against `frontend/src`. It builds on [PHASE_8_DESIGN_CRITIQUE.md](PHASE_8_DESIGN_CRITIQUE.md). Part A lists today's violations in the skill's `file:line` format. Part B is the standard that Phase 8 code must meet.

## Part A: compliance audit of the current frontend

### src/components/ui.jsx
- `ui.jsx:69` `inputCls` uses `outline-none`; `focus:border-accent` is the only replacement, so the focus is barely visible. Use `focus-visible:ring-*`.
- `ui.jsx:52` `transition` is not property-scoped. List the properties: `transition-[background-color,border-color,color]`.
- `ui.jsx:121` `<tr onClick>` is a clickable row with no keyboard access. Add a row `<button>`/`<Link>`, or `tabIndex=0` plus Enter/Space.
- `ui.jsx:62` `Field` wraps the control in a `<label>` (good), but the hint is not linked. Add `aria-describedby`.
- `ui.jsx:73,80` Loading/ErrorBox have no `aria-live` / `role="status"` / `role="alert"`.

### src/components/Layout.jsx
- `Layout.jsx:88,94,96` icon-only buttons (refresh, switch profile, sign out) use `title` only. Add `aria-label`; their icons need `aria-hidden`.
- `Layout.jsx:25` `window.confirm` for sandbox reset. Use an app modal with a clear consequence and focus trap.
- `Layout.jsx:54` fixed `w-60` sidebar with no breakpoint behaviour, so the main column is 135 px at 375 px.
- No skip link to `<main>`.
- `Layout.jsx:57` sidebar labels at 10 px uppercase in `text-faint` fail contrast (3.1–3.6:1).

### src/components/ChatPanel.jsx
- `ChatPanel.jsx:120` composer input `outline-none` with no `focus-visible` replacement.
- The streaming answer region has no `aria-live="polite"`, so screen readers don't hear the final answer.

### src/pages/*
- `Transactions.jsx:87`, `Credit.jsx:112`, `Plan.jsx:275`, `ModelLab.jsx:144` `outline-none` on inputs and selects.
- `Transactions.jsx:90`, `Plan.jsx:390` click handlers on non-button elements.
- `Records.jsx:162,165`, `Review.jsx:61`, `Statements.jsx:270,318`, `DataManagement.jsx:23` use `window.confirm` for destructive actions. Use a modal with an explicit consequence, or an undo window.
- `SignIn.jsx:46` `autoFocus` is justified (the single primary input on desktop). Keep it, but skip it on coarse pointers.
- Inputs: 21 controls but only 17 label, `htmlFor` or `aria-label` usages, so some filters (Transactions, Insights) have no accessible name.
- URL state: filters, tabs and periods (Insights, Transactions) live in `useState` only, so they can't be deep-linked or restored with Back.

### src/format.js, src/index.css, index.html
- `format.js` `toFixed`-based ₹ formatting (L/Cr) is acceptable: Indian units are not covered by `Intl` compact notation. Keep it, but use `Intl.NumberFormat('en-IN')` for plain numbers (already the case). `monthLabel` uses a hardcoded month array; prefer `Intl.DateTimeFormat('en-IN', {month: 'short'})`.
- `index.css:29` `color-scheme: dark` is set; Phase 8 switches to `light`. There is no `<meta name="theme-color">`.
- Good: `.num` gives `tabular-nums`, `.rise` honours `prefers-reduced-motion`, and the viewport meta does not block zoom.

## Part B: Finora standards for Phase 8

### 1. Layout
- **Shell:** navigation rail plus content.
  - ≥1280 px: labelled sidebar of 232 px.
  - 768–1279 px: icon rail of 72 px with tooltips plus labels.
  - <768 px: top bar with a menu button that opens a drawer, and the main area full width.
- **Content width:** max 1120 px for reading pages and 1280 px for tables; centred, with `px-6` (desktop) or `px-4` (mobile) gutters.
- **One column of meaning per screen:** a page header (title, one-sentence purpose, at most 2 actions), then sections separated by 48 px of whitespace and a heading. No cards nested in cards.
- **Second-level navigation:** tabs under the page header, synced to the URL (`?tab=`).
- **Grid:** 12 columns, 24 px gutters; stat rows have at most 3 items on desktop.

### 2. Typography

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| display | 32/40 | 600 | Home greeting, one per screen |
| title | 24/32 | 600 | Page title (`h1`) |
| heading | 18/26 | 600 | Section (`h2`) |
| subheading | 15/22 | 600 | Card / group (`h3`) |
| body | 15/24 | 400 | Default text |
| small | 13/20 | 400–500 | Labels, table cells, captions |
| micro | 12/16 | 500 | Badges, overlines (minimum size; nothing below 12 px) |

- Numbers use `tabular-nums`; headline figures use the `title` or `display` size, never more than 3 per view.
- Headings use `text-wrap: balance` and body text `text-pretty`.
- Copy: active voice, second person, "…" for loading states ("Loading your plan…"), specific button labels ("Import Statement", not "Continue"), and errors that say how to fix them.

### 3. Spacing
A 4 px base scale: 4, 8, 12, 16, 24, 32, 48, 64. Component padding is 16 or 24; section gap 48; inline gap 8 or 12.

### 4. Breakpoints
`sm` 640, `md` 768, `lg` 1024, `xl` 1280 (Tailwind defaults). Every page is verified at 375, 768, 1280 and 1440 with no horizontal scroll.

### 5. Navigation behaviour
- Six areas (Home / Plan, Money, Future, Risk & Models, Ask, Data), plus Settings in the account menu.
- The active area and tab are always visible, and links are real `<Link>`s, so Cmd/Ctrl-click works.
- A badge count appears only for actionable items (findings to review, transactions to check).
- **Ask** is reachable from everywhere: a header button opens the panel, and "Ask about this" on findings, figures and models pre-fills a question.
- Profile switcher and sign-out live in one account menu (keyboard and screen-reader accessible).

### 6. Accessibility (WCAG 2.2 AA)
- **Contrast:** at least 4.5:1 for text and 3:1 for UI components and focus rings. The light tokens in the theme are chosen to pass.
- **Focus:** every interactive element gets `focus-visible:ring-2 ring-accent ring-offset-2`, and `outline-none` is never used without it.
- **Semantics:**
  - one `h1` per page;
  - a skip link to `#main`;
  - `<main>`, `<nav aria-label>`, `<table>` with `<th scope>`;
  - icon-only buttons have an `aria-label`, and their icons `aria-hidden`.
- **Live regions:** a `role="status"` for loading, toasts and streaming answers (polite), and `role="alert"` for errors.
- **Targets:** at least 44×44 px on touch (`pointer: coarse`) and at least 32 px on desktop.
- **Charts:** each has a one-sentence text summary and a "View as table" toggle; colour is never the only signal.
- **Motion:** `prefers-reduced-motion` disables all non-essential motion.

### 7. Forms
- Visible label above every field; hints linked via `aria-describedby`; correct `type`, `inputMode`, `autocomplete` and `name`.
- Validate on blur and on submit. Errors appear inline under the field, and the first invalid field gets focus.
- The primary button stays enabled until submit, then shows a spinner ("Saving…").
- Forms with unsaved changes warn before navigation.
- Money inputs accept "₹1.5 lakh" style where the backend parser already supports it, and otherwise show the format as a placeholder ending in "…".

### 8. Tables (Stripe pattern)
- **Toolbar:** search, filter chips and a period selector, all synced to the URL; plus export.
- **Rows:**
  - 48 px high, text left-aligned and numbers right-aligned with `tabular-nums`;
  - a hover background and a full-row link or button opening a **detail drawer**;
  - inline controls only for single-click actions such as accept/reject.
- **Size:** paginate or virtualise beyond 50 rows.
- **Empty, loading and error states** are designed per table: a skeleton, an empty message with the next action, and an error message with Retry.

### 9. Buttons
- **Primary:** filled accent, one per view.
- **Secondary:** white with a border.
- **Quiet:** text-only.
- **Destructive:** red text or border; the filled red version appears only inside a confirm dialog.
- Sizes 32 / 40 / 44 px. Every button has a label or an `aria-label`. Disabled buttons explain why (a tooltip or helper text).

### 10. Inputs
40 px high, 1 px border, 8 px radius, a visible focus ring, a light grey placeholder (still ≥4.5:1 for typed text) and an error state with a red border plus a message.

### 11. Modals and drawers
- **Modals** are for confirmations only. They state the title as an action ("Delete 3 transactions?") and the consequence, with Cancel and a specific action button.
- **Drawers** (right side, 480 px; full screen on mobile) are for detail and editing.
- Both trap focus, close on Esc and on a backdrop click (drawers), restore focus to the trigger, and use `overscroll-behavior: contain`.
- All `window.confirm` calls are replaced.

### 12. Loading states
- A skeleton matching the final layout for the first load, and inline spinners for actions.
- No full-page blocking spinner after the first load.
- Long operations show real progress: statement import already reports progress, so use it.
- The AI CFO keeps its real stream stages (Understanding → Fetching → Writing → Correcting).

### 13. Empty states
- Each one has an icon or illustration, one sentence saying what will appear here, and the action that fills it ("Import a statement", "Add an account").
- Never a broken chart or "—" wall: a missing-data section shows what is missing and how to add it (keeps the Phase 3 "honest pages" rule).

### 14. Error states
- **Inline:** the field or section, with Retry.
- **Page:** a friendly title, what happened, and what to do.
- **Network:** a toast with Retry.
- The AI CFO keeps its "nothing was saved" interruption copy.
- Raw exception text is never shown.

### 15. Interaction feedback
- Hover, active and focus states are each more prominent than the rest state.
- Toasts confirm saves and undo-able actions ("Category changed · Undo").
- Optimistic UI only where the backend supports undo.
- Transitions run 150–200 ms on `opacity` / `transform`, with no `transition: all`.

### 16. Keyboard navigation
- Full tab order follows the visual order.
- `/` focuses search on table pages, `Esc` closes overlays, and Enter on a row opens the detail view.
- In Ask, Enter sends, Shift+Enter adds a newline, and Esc stops a streaming answer.

### 17. Content honesty (Finora-specific, mandatory)
- Every model output uses the **trust component**: status chip (Accepted / Experimental / Suggestion only), a one-line limitation, and "How this was measured" linking to Model Lab.
- Verified facts and model suggestions are visually distinct: facts are plain, while suggestions carry the chip and "suggested" wording.
- Persistent copy: "Synthetic demo data" in demo sandboxes, and "Educational guidance, not licensed advice" in the footer of Plan and Ask.

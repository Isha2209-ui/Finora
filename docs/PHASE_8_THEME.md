# Phase 8 theme: "Finora Daylight"

**Source.** Produced with `/theme-factory` using its "Create your own theme" path. None of the 10 preset themes fits the approved direction. The closest are **Modern Minimalist** (charcoal `#36454f`, grey scale, white) and **Arctic Frost** (steel blue `#4a6fa5`, ice-blue highlights, crisp white). Finora Daylight combines Modern Minimalist's charcoal-on-white restraint with Arctic Frost's steel-blue accent. Every value was then tuned so that every text and control pair passes WCAG AA, using the contrast figures computed below.

**Status.** A proposal for owner review. It is **not applied** to the code; it will be applied at stage 8.4 after approval.

**Character.** Bright white, calm and precise, in the spirit of Apple-like refinement with Stripe-like clarity. Colour is reserved for meaning: the accent marks actions and the current location, and green, amber and red mark status only. Most of the screen is white, charcoal and grey.

## 1. Colour tokens (contrast measured against white / canvas / subtle)

| Token | Hex | Contrast | Use |
|---|---|---|---|
| `bg` | `#ffffff` | — | Content surfaces |
| `canvas` | `#f7f8fa` | — | App background behind content, sidebar |
| `subtle` | `#f1f3f6` | — | Hover rows, table header, segmented-control track |
| `line` | `#e4e7ec` | (decorative) | Dividers, card borders |
| `line-strong` | `#c9cfd8` | (decorative) | Table header bottom, separators that must be seen |
| `control` | `#868e9e` | 3.29 / 3.10 | Input, checkbox and select borders (≥3:1, WCAG 1.4.11) |
| `ink` | `#1d2433` | 15.5 / 14.6 / 14.0 | Primary text, headline figures |
| `ink-2` | `#3d4656` | 9.5 / 9.0 / 8.6 | Body copy |
| `muted` | `#5b6475` | 6.0 / 5.6 / 5.4 | Secondary text, labels |
| `faint` | `#656d7f` | 5.2 / 4.9 / 4.7 | Captions, provenance, honesty notes (the smallest text that still passes) |
| `accent` | `#3157c8` | 6.3 / 5.9 / 5.7 | Primary buttons, links, active nav, focus ring; white on accent is 6.3 |
| `accent-hover` | `#2745a3` | 8.5 | Hover and pressed state |
| `accent-soft` | `#eef2fc` | accent text on it: 5.6 | Selected nav item, info notes, chip background |
| `good` / `good-soft` | `#13794a` / `#ecf8f1` | 5.4 / 5.0 on soft | Positive status, "Accepted" chip |
| `warn` / `warn-soft` | `#a15c07` / `#fef6e7` | 5.2 / 4.8 on soft | "Experimental", attention needed, demo banner |
| `bad` / `bad-soft` | `#c4320a` / `#fef1ec` | 5.5 / 5.0 on soft | Errors, destructive actions, overspend |

Rules:
- Status colour is always paired with an icon or word, never colour alone.
- Negative money is shown as "−₹", in `ink`, not red, unless it is a status (overspend, a loss on an investment).

## 2. Chart palette (≥3:1 against white for graphical objects)

`#3157c8` blue (6.3), `#0e8074` teal (4.8), `#6e52d9` violet (5.4), `#b8640a` amber (4.3), `#c0396b` rose (5.2), `#667085` slate (5.0, used for "Other").
- Model **baseline** lines use `#8a92a2` (3.1), dashed and labelled. The lighter `#98a2b3` (2.6) was rejected.
- At most 5 series per chart, plus "Other".
- Gridlines use `line`, and axis text uses `faint` at 12 px.
- Forecast bands use an accent tint at 12% opacity.

## 3. Typography

| | |
|---|---|
| Typeface | **Inter** (already loaded; variable weights 400/500/600), with system fallback `-apple-system, "SF Pro Text", "Segoe UI", Roboto`. No new font dependency. |
| Numbers | `font-variant-numeric: tabular-nums`, letter-spacing −0.01em (the existing `.num` class) |
| Tracking | Display and title −0.02em; body 0; micro uppercase overlines +0.06em |
| Scale | display 32/40 · title 24/32 · heading 18/26 · subheading 15/22 · body 15/24 · small 13/20 · micro 12/16 (12 px minimum) |
| Weights | 400 body · 500 labels and figures · 600 headings and headline figures |

## 4. Spacing, radius, elevation, motion

- **Spacing (4 px base):** 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64.
- **Radius:**
  - `sm` 6 px (chips, badges);
  - `md` 8 px (buttons, inputs);
  - `lg` 12 px (cards, tables);
  - `xl` 16 px (drawers, modals, the Ask composer);
  - `full` (avatars, pills).
- **Shadows** (minimal; most surfaces use a 1 px `line` border instead):
  - `shadow-xs` `0 1px 2px rgba(16,24,40,.05)` for buttons and inputs;
  - `shadow-sm` `0 1px 3px rgba(16,24,40,.08), 0 1px 2px rgba(16,24,40,.04)` for raised cards (only where needed);
  - `shadow-overlay` `0 12px 32px rgba(16,24,40,.12), 0 4px 8px rgba(16,24,40,.04)` for drawers, modals and menus.
- **Motion:** 150 ms (hover, press), 200 ms (drawers, tabs), easing `cubic-bezier(.2,.8,.2,1)`, `opacity` / `transform` only, all off under `prefers-reduced-motion`.
- **Focus ring:** 2 px `accent`, offset 2 px (`focus-visible` only).

## 5. Gradients (selective: exactly two places)

1. **Home greeting band:** `linear-gradient(180deg, #f3f6fe 0%, #ffffff 100%)` behind the welcome and priorities. A barely-there tint that marks "start here".
2. **Ask:** a 1 px top border and the send button with `linear-gradient(135deg, #3157c8, #6e52d9)`, marking the AI as a distinct but quiet capability.

No gradients on cards, buttons in general, tables or charts.

## 6. Components (theme application)

| Component | Spec |
|---|---|
| **Button: primary** | `accent` fill, white 15 px/500 text, `md` radius, heights 32 / 40 / 44, `shadow-xs`; hover `accent-hover`; disabled at 50% with a reason |
| **Button: secondary** | white, 1 px `control` border, `ink` text; hover `subtle` |
| **Button: quiet** | text `accent`; hover underline |
| **Button: destructive** | `bad` text and border; filled `bad` only inside the confirm modal |
| **Input / select** | 40 px, white, 1 px `control` border, `md` radius, `ink` text, placeholder `faint`; focus: accent ring; error: `bad` border plus message |
| **Card / section** | white, 1 px `line` border, `lg` radius, 24 px padding, no shadow; never nested |
| **Stat** | label `small` `muted`, value `title` `ink` tabular, optional delta chip; at most 3 per row |
| **Navigation** | `canvas` sidebar; items 40 px, 14 px/500 `ink-2`, icon 18 px `muted`; active: `accent-soft` background, `accent` text and icon, plus a 2 px accent indicator; group headings `micro` uppercase `faint` |
| **Tabs** | underline style: `ink` active text with a 2 px accent underline; inactive `muted`; URL-synced |
| **Table** | header `subtle`, 12 px/500 `muted` uppercase micro; rows 48 px, `line` dividers, hover `subtle`; numbers right-aligned tabular |
| **Chip / trust component** | `sm` radius, 12 px/500; Accepted = good-soft/good, Experimental = warn-soft/warn, Suggestion only = accent-soft/accent; plus a one-line limitation in `faint` and a "How this was measured →" quiet link |
| **Drawer** | right, 480 px, white, `shadow-overlay`, `xl` radius on the leading corners, header with title and close button (aria-labelled) |
| **Modal** | 440 px, centred, `shadow-overlay`, title as a question, consequence text, Cancel (secondary) plus action (primary or destructive) |
| **Toast** | bottom-centre, `ink` background, white text, optional Undo (quiet, white) |
| **Demo banner** | `warn-soft` background with `warn` text and icon, 36 px, dismissible per session but always present as a chip in the header |

## 7. Tailwind v4 tokens (to replace the `@theme` block in `frontend/src/index.css` at stage 8.4)

```css
@theme {
  --color-bg: #ffffff;      --color-canvas: #f7f8fa;   --color-subtle: #f1f3f6;
  --color-line: #e4e7ec;    --color-line-strong: #c9cfd8; --color-control: #868e9e;
  --color-ink: #1d2433;     --color-ink-2: #3d4656;    --color-muted: #5b6475;  --color-faint: #656d7f;
  --color-accent: #3157c8;  --color-accent-hover: #2745a3; --color-accent-soft: #eef2fc;
  --color-good: #13794a;    --color-good-soft: #ecf8f1;
  --color-warn: #a15c07;    --color-warn-soft: #fef6e7;
  --color-bad: #c4320a;     --color-bad-soft: #fef1ec;
  --color-chart-1: #3157c8; --color-chart-2: #0e8074; --color-chart-3: #6e52d9;
  --color-chart-4: #b8640a; --color-chart-5: #c0396b; --color-chart-other: #667085; --color-chart-baseline: #8a92a2;
  --font-sans: "Inter", -apple-system, "SF Pro Text", "Segoe UI", Roboto, ui-sans-serif, system-ui, sans-serif;
  --text-display: 2rem;  --text-display--line-height: 2.5rem;
  --text-title: 1.5rem;  --text-title--line-height: 2rem;
  --text-heading: 1.125rem; --text-heading--line-height: 1.625rem;
  --text-body: 0.9375rem; --text-body--line-height: 1.5rem;
  --text-small: 0.8125rem; --text-small--line-height: 1.25rem;
  --text-micro: 0.75rem; --text-micro--line-height: 1rem;
  --radius-sm: 6px; --radius-md: 8px; --radius-lg: 12px; --radius-xl: 16px;
  --shadow-xs: 0 1px 2px rgba(16,24,40,.05);
  --shadow-sm: 0 1px 3px rgba(16,24,40,.08), 0 1px 2px rgba(16,24,40,.04);
  --shadow-overlay: 0 12px 32px rgba(16,24,40,.12), 0 4px 8px rgba(16,24,40,.04);
  --ease-out: cubic-bezier(.2,.8,.2,1);
}
```

**Migration note.** Existing class names (`bg-bg`, `text-ink`, `text-muted`, `text-faint`, `border-line`, `bg-accent`, `text-good`/`warn`/`bad`) keep working with the new values, so the switch is incremental. `bg-surface` and `bg-raised` map to `bg` and `subtle` during the transition and are then removed. `color-scheme` becomes `light`, and `<meta name="theme-color" content="#f7f8fa">` is added.

## 8. Revision: model chip

The trust chip in §6 is now a **model identity chip**: an accent-soft "Model: {algorithm}" badge followed by a quiet "How it works" link that opens a drawer. Status tones (Accepted / Experimental / Suggestion only) are no longer used in the interface. The tokens are unchanged.

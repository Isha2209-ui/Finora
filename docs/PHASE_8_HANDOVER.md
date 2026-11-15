# Phase 8 handover: Product shell and UI (historical: written before Phase 8)

> **Superseded.** Phase 8 has since been designed and implemented. See [PHASE_8_DESIGN_SPECIFICATION.md](PHASE_8_DESIGN_SPECIFICATION.md) and [PHASE_8_VERIFICATION.md](PHASE_8_VERIFICATION.md). This note is kept as the pre-Phase-8 record.

Phase 8 is the owner's to implement. This note records the intended design direction and the integration points that
Phases 6 and 7 leave behind. **Nothing in this document has been implemented.**

## 1. Design philosophy

Finora should feel like a premium personal financial-intelligence product. It should be:
- minimal, intelligent and calm;
- personal and guided;
- trustworthy, modern and precise.

It should not look like banking or accounting software. Avoid:
- excessive cards, charts, metrics and repeated widgets;
- generic admin-dashboard layouts;
- navigation sprawl and information overload.

## 2. Guided journey (Finora Plan stays central)

1. **Where I stand:** the picture, with one sentence and a few numbers.
2. **What matters and why:** the diagnosis, each item with its evidence.
3. **The next meaningful action:** ranked actions.
4. **Its impact:** the scenario engine, baseline vs plan.
5. **Progress over time.**

Use progressive disclosure: detail, method and model provenance one click away, never in the way.

## 3. Today's UI and its constraints

- **Stack:** React 19, Vite, Tailwind, recharts, lucide icons. Shared components are in `frontend/src/components/ui.jsx` (Card, Stat, Badge, Note, KV, Table, …). Colour tokens are in `index.css`.
- **Navigation** is a long sidebar (`components/Layout.jsx`) with 5 groups and about 25 pages. Phase 6 added three pages:
  - **Anomaly Scanner** (`/scanner`);
  - **Peer Benchmarking** (`/peers`);
  - **Model review** (`/models/review`).

  The sidebar is the main candidate for consolidation.
- **Product rule (owner, 2026-11-15): every built feature must stay visible and usable.** A redesign may regroup features, but it must not hide any of them, including:
  - Credit Risk (with the "Score a card history" form);
  - Peer Benchmarking;
  - Transaction Categorisation (accept/reject suggestions);
  - the Anomaly Detection Scanner;
  - Cash-Flow Forecasting (with its baseline);
  - Model Lab and the blinded review.
- **Honesty labels must survive any restyle:**
  - experimental and not-human-validated status;
  - forecast vs 3-month baseline;
  - US / Taiwan / not-Indian scope;
  - "suggested" categories;
  - "unusual is not fraud".
- **Data loading:** pages read one cached analysis (`store.jsx`, `GET /api/profiles/{id}/analysis`). Each ML output carries `model_info` (version, `accepted`/`experimental`, unmet criteria, evaluation), which a redesign can surface uniformly, for example as a single trust chip.

## 4. AI CFO integration points (Phase 7)

| Point | Where | Notes |
|---|---|---|
| Streaming chat | `POST /api/profiles/{id}/chat/stream` | NDJSON events: `status`, `plan` (with `interpretation`), `tool`, `draft` (never an answer), `final` (same fields as /chat), `error`. Only `final` is saved; Stop aborts and saves nothing. Used by `ChatPanel.jsx`. |
| Chat API | `POST /api/profiles/{id}/chat` | Returns `answer`, `engine`, `mode` (general/personal), `tools_used`, `tool_calls` (arguments), `verified`, `notice`, `trace` (latency, tokens/s, number check). History: `GET` / `DELETE` same path, per account and per profile. |
| Model status | `GET /api/cfo/status` | Local model name, availability, reason when offline. |
| Briefing | `GET /api/profiles/{id}/briefing` | Monthly briefing, priorities and alerts. |
| UI | `components/ChatPanel.jsx` (side panel on every page, plus full page `/cfo`) | Shows tools used, sources, verification, general vs personal, latency, and the offline notice. |
| Tools | `backend/app/cfo/tools.py` `REGISTRY` | Read-only, bound to the signed-in profile. Adding a tool = function + description + argument schema. |

### Natural Phase 8 placements for the assistant

- **Contextual entry points:** a "Ask about this" on each Plan finding or action, pre-filling a question.
- **Visible on every page:** the assistant as a calm persistent affordance rather than a separate chatbot page.
- **Clickable sources:** sources (`tool_calls`) rendered as links to the page that shows the same figure, e.g. `spending` → Transaction Intelligence filtered to that month and category.
- **Latency:** median about 8–11 s, worst about 60 s on the 8 GB M2 (Phase 7 final evaluation). Streaming is implemented; a Phase 8 restyle should keep the progress states, the 'Draft, being checked' label and the Stop button.

## 5. Suggested starting point

1. Consolidate navigation around the Plan:
   - **Plan** (home);
   - **Money**: accounts, transactions, statements, insights, review;
   - **Future**: forecast, FIRE, decisions;
   - **Risk & models**: credit, scanner, peers, Model Lab;
   - **Ask** (the AI CFO);
   - **Data & settings**.
2. Define one trust component (status + limitation + "how this was measured") and use it on every model output.
3. Restyle page by page, keeping every API contract unchanged. The backend needs no change for a UI-only Phase 8.

# Phase 8 browser tests (Playwright CLI)

Each file is a Playwright function run against the **real running app** (API on :8001, Vite on :5173). They use the real backend and real data; nothing is mocked except one deliberately simulated failure in `p8_ask.js`.

```bash
playwright-cli open                                   # once
playwright-cli --raw run-code --filename=e2e/p8_smoke.js
playwright-cli --raw run-code --filename=e2e/p8_functional.js
playwright-cli --raw run-code --filename=e2e/p8_responsive.js
playwright-cli --raw run-code --filename=e2e/p8_registration.js
playwright-cli --raw run-code --filename=e2e/p8_ask.js    # needs Ollama with qwen2.5:3b
```

| Script | Covers |
|---|---|
| `p8_smoke.js` | Sign-in validation, invalid credentials, registration, demo path; every area and tab (one `h1`, selected tab, no crash); all 18 old-route redirects; back/forward; refresh on a tab URL |
| `p8_functional.js` | Transactions search/sort/pagination/drawer/recategorise (persisted after refresh); add and delete a transaction; spending views and filters; accept/reopen a recommendation; tax calculator and validation; add/delete a goal; what-if, retirement, payoff; credit-risk scoring; categoriser; Model Lab deep link; statement import end to end with undo; profile edit persisted; security activity; honest Settings |
| `p8_responsive.js` | Private profile (empty state, data persisted), cross-account isolation (404s from a second, independent browser context), demo and private coexisting; 10 pages × 4 viewports (overflow, nav form, one `h1`, named buttons, labelled inputs); mobile drawer; skip link; tab arrow keys; focus ring; sign-out and sign-back-in; screenshots into `docs/phase8-screenshots/` |
| `p8_registration.js` | 20 consecutive sign-ups through the form from one IP; duplicate e-mail rejected; independent sign-in; sign-out protects routes; another account's private profile returns 404 |
| `p8_ask.js` | AI CFO streaming stages, checked final answer, follow-up in context, Stop (Esc) with nothing saved, history after reload, error handling, header panel, "Ask about this" pre-fill without sending |

Each run registers fresh test accounts (`*@finora.test`). Sign-ups are not rate-limited by default (`REGISTER_IP_MAX=0`).

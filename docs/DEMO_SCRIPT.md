# Finora demo script (12–15 minutes)

**Before you start (5 minutes ahead):**
- Ollama is running and the model is warm: `ollama run qwen2.5:3b "hi"`, then exit.
- Finora is running: `./run.sh`.
- Open http://localhost:5173 in a 1440 px wide window.
- Have a second browser profile or a private window ready for the isolation step.
- Optional: a bank CSV, or use the built-in synthetic sample.

Each step gives **Click** (what to do), **Say** (what to explain) and **Point at** (what the audience should notice). The numbers quoted are those of the demo person *Aarav Mehta* (`ABCDE1234F`) on the current data. If the data changes, read them from the screen; never quote from memory.

---

## 1. Sign up and start (1 min)
- **Click:** "Create an account". Enter a name, an e-mail and a 10+ character password. Then Create account.
- **Say:**
  - Accounts are local.
  - Passwords are hashed with argon2id.
  - The session is an httpOnly cookie, and every change needs a CSRF token.
  - There is no e-mail verification or CAPTCHA in this local build.
- **Point at:** the Start screen, which offers a demo person or your own empty profile.
- **Click:** **Aarav Mehta**.
- **Say:** this opens a private *copy* of a fictional person (synthetic data, clearly labelled). Edits only touch your copy; Reset restores it.

## 2. Home: answer first (1 min)
- **Point at:** the greeting, the one-sentence status and the top three priorities, each with its reason.
- **Say:**
  - Every page starts with the answer, then the facts, then the detail.
  - The badge on Plan counts open alerts.

## 3. Money overview, accounts and transactions (2 min)
- **Click:** Money.
  - **Point at:** net worth (₹29.77 L for Aarav), assets and liabilities.
- **Click:** Accounts & cards.
  - **Point at:** the two bank balances (HDFC ₹1.86 L, SBI ₹2.42 L).
- **Click:** Transactions. Type "Haldiram" in Search, then sort by amount.
- **Say:** search, sort and paging run on the server, and the filters live in the URL so Back and Refresh keep them.
- **Click:** a row.
  - **Point at:** the drawer showing the source, category and how the category was decided.
  - Change the category and say it persists after refresh.

## 4. Goals and planning (2 min)
- **Click:** Plan → Goals.
- **Point at:** each goal's progress and the two monthly amounts. For example, the car goal needs ₹38,505 a month with 7% assumed growth, or ₹40,000 with none.
- **Click:** "How the monthly amounts are worked out".
  - **Say:** 7% is a planning assumption, not a promised return. 0% shows the no-growth case.
- **Click:** Add. Try a past date and Save.
  - **Point at:** the error inside the form.
  - Fix the date and Save; the new goal's amounts appear immediately.
- **Click:** Plan → Priorities / Actions.
  - **Say:** actions are ranked by a published formula; each one shows its effect on surplus, runway and the debt-free date.

## 5. Future (1.5 min)
- **Click:** Future → Cash flow.
  - **Point at:** the forecast (₹70,044 next month, range ₹36,260 – ₹1,03,827) beside the 3-month average.
  - **Say:** the model is shown *with* its baseline because on its own test it did not beat that average. Finora says so.
- **Click:** What-if.
  - Price ₹9,00,000, down payment ₹2,00,000, then "Should I buy it?".
  - **Point at:** the verdict and the fixed rules it follows (EMI share, runway, savings rate).
  - **Say:** no AI decides the verdict.
- **Click:** Retirement.
  - **Point at:** the FIRE number = yearly spending ÷ withdrawal rate. Change "Invest each month" and watch the age move.

## 6. The six ML capabilities (3 min)
- **Click:** Risk & Models.
  - **Point at:** the six rows, each with the algorithm, what it is for and *your* result.
- **Credit Risk** (XGBoost + SHAP):
  - **Point at:** 7.5%, low risk, and the bars showing which inputs raise or lower it.
  - **Click:** How it works.
  - **Say:** trained on 30,000 real Taiwanese card accounts; it is not a bureau score.
- **Peer Benchmarking** (K-Means):
  - **Point at:** the peer group and "better than X%".
  - **Say:** clusters of US households from the Federal Reserve's 2022 survey.
- **Transaction Categoriser** (TF-IDF + logistic regression):
  - **Click:** Try it, then type a narration.
  - **Point at:** the confidence.
  - **Say:** under 0.5 it goes to Review; it is never silently applied.
- **Anomaly Detection Scanner** (Isolation Forest):
  - **Point at:** 4 flagged transactions, each with a reason, e.g. "41.3× your typical Dining transaction".
  - **Say:** unusual *for you*, compared with your own history; not fraud detection.
- **Cash-Flow Forecast:** already shown in step 5.
- **Model Lab:**
  - **Point at:** versions, datasets with licences, training time, metrics, and the acceptance checks with pass/fail.
  - **Say:** each artefact is checksum-verified at load.

## 7. AI CFO, running locally (2 min)
- **Click:** Ask, then ask "What is my net worth?"
  - **Point at:** the progress stages, then the answer (₹29,76,808), "Understood as", "Figures checked" and the model name and time.
- **Ask:** "And how much did I spend on dining last month?", then "What about the month before?"
  - **Say:** follow-ups keep context.
- **Ask:** "Delete all my transactions."
  - **Point at:** the read-only reply.
  - **Say:** the assistant's tools only read; it cannot change data and never claims to.
- **Ask:** "Which mutual funds should I buy?"
  - **Point at:** it does not pick stocks or funds.
- **Say:**
  - Qwen 2.5 3B runs on this laptop through Ollama; nothing goes to a cloud model.
  - Every number in an answer is checked against the computed figures before it is shown; if a check fails, a rule-based answer is shown instead.

## 8. Import and reports (1.5 min)
- **Click:** Data → Import → "Try a synthetic sample".
  - **Point at:** the detected layout, column mapping and preview, then Import.
  - **Say:** duplicates and overlaps are detected, and Undo restores the profile exactly.
- **Optional:** drop a non-statement file to show the clear refusal ("Could not find a header row…").
- **Click:** Reports → Generate PDF.
  - **Say:** it is the same numbers as the screens, and also available as CSV and a full zip export.

## 9. Privacy and isolation (1 min)
- **Click:** Data → Profile & privacy.
  - **Point at:** what is stored, Export, Reset demo, and Delete.
- **Click:** the account menu → Sign out. Then open http://localhost:5173/money; you are sent to sign-in.
- **Say:**
  - Another account cannot open this profile: the server answers 404 for every profile route.
  - Phase 9 tested this automatically on all 53 profile-scoped endpoints, including someone else's transaction, goal, import, rule, recommendation and assumption ids.

---

**If something goes wrong live:**
- If the AI CFO is slow, the first answer after a cold start can take 20–60 s, so warm the model first. If Ollama is stopped, the assistant answers in calculator mode and says so.
- If the port is busy, only one backend may run per database (a lock is enforced). Stop the other one.

# Finora: ML model provenance report

This report covers the six machine-learning capabilities as they exist in the code on `master`. Every figure below is copied from the shipped artefacts:
- `backend/artifacts/active.json` (which version is live and why);
- `backend/artifacts/real/<model>/<version>/provenance.json`;
- `backend/artifacts/real/<model>/<version>/metrics.json`.

Nothing is estimated or rounded beyond what those files contain. Fuller acquisition and training notes are in [PHASE_6_DATA_ACQUISITION.md](PHASE_6_DATA_ACQUISITION.md) and [PHASE_6_TRAINING.md](PHASE_6_TRAINING.md).

## How a model gets to the screen

1. **Train and evaluate.** `python -m app.ml.train <model> --approved` (from `backend/`) reads the raw dataset in `backend/datasets/raw/`. It writes `model.joblib`, `metrics.json` and `provenance.json` into a new versioned folder, and never activates anything.
2. **Check acceptance.** `python -m app.ml.train check` runs the predefined criteria in `app/ml/acceptance.py` against every trained version.
3. **Activate.** `python -m app.ml.train activate <model> <version> --reason "…"` records the version, its SHA-256 and the reason in `active.json`.
4. **Load.** At start-up, `app/ml/registry.py` loads the active artefact and verifies its checksum. Every output the API returns carries `model_info` (model, version, status).
5. **Present.** The interface shows the algorithm, a "How it works" explanation and the user's own result (`frontend/src/components/models.js`). Model Lab (`/models?tab=lab`) shows versions, datasets, training runs, metrics and acceptance checks.

**Ownership boundary.** Private profiles are never used for training; this is enforced by `test_private_profiles_are_never_used_for_training`. Raw datasets are not in the repository (`.gitignore`). The trained artefacts are, so a fresh copy runs without retraining.

## Summary

| # | Capability | Algorithm | Training data (real) | Live version | Acceptance |
|---|---|---|---|---|---|
| 1 | Credit Risk | XGBoost classifier + SHAP TreeExplainer | UCI "Default of Credit Card Clients", 30,000 accounts, Taiwan 2005 | `v20261114-211415` | Passed (beats logistic regression on test ROC-AUC) |
| 2 | Peer Benchmarking | Weighted K-Means (k = 3) | Federal Reserve SCF 2022, 4,595 US families × 5 implicates | `v20261114-215812` | Passed (ARI ≥ 0.70, silhouette > 0, weights sum to 100%) |
| 3 | Transaction Categoriser | TF-IDF (char 2–5-grams + words) + logistic regression | Oklahoma PCard FY2021–24 (train), DC PCard and MoneyVis (independent tests) | `v20261114-222418` | Passed (4 of 4 criteria) |
| 4 | Anomaly Detection Scanner | Isolation Forest (300 trees) | Oklahoma PCard FY2021–23 (train), FY2024 (chronological test) | `v20261114-222608` | Technical stability passed; human-review criterion **not yet met** (review not done) |
| 5 | Cash-Flow Forecast | XGBoost regressor | MoneyVis, one real UK person's account, 2015–2022 | `v20261114-215913` | **Not met**: does not beat the 3-month average (MAE 856.93 vs 809.49) |
| 6 | Model Lab and provenance | n/a (registry, checksums, metrics, review workspace) | n/a | n/a | n/a |

The status field in `active.json` remains `experimental` for capabilities 4 and 5. The interface no longer shows development-stage badges, but nothing on screen claims these two are validated. The forecast is always shown beside the 3-month average it is compared with.

---

## 1. Credit Risk: XGBoost + SHAP

| | |
|---|---|
| **Implementation** | `backend/app/ml/credit_risk.py` (inference, SHAP) · `backend/app/ml/real/` training · `POST /api/models/credit-risk/score` (what-if form) and `analysis.ml.credit_risk` (per card) |
| **Input features (14)** | Age; latest payment status; payment status 2 and 3 months ago; worst payment delay (6 months); months with a delayed payment; months paying only part of the bill; months paid in full; latest credit utilisation; average utilisation (6 months); utilisation trend; share of last bill repaid; average share of bill repaid; months with no payment made. Demographic columns (sex, education, marriage) are dropped on purpose. Money columns become ratios to the credit limit. |
| **Dataset** | "Default of Credit Card Clients", Yeh & Lien (2009), UCI ML Repository, DOI 10.24432/C55S3H, CC BY 4.0. 30,000 records; Taiwan, April–September 2005 (target: October 2005). The local copy was verified cell-for-cell against the official file. |
| **Training** | `python -m app.ml.train credit_risk`. Stratified 70/15/15 train/validation/test split with 5-fold CV on the training part. The decision threshold (0.26) is chosen to maximise F1 on validation only. Trained 2026-11-14 in 3.0 s, peak memory 219.5 MB. |
| **Artefact** | `real/credit_risk/v20261114-211415/model.joblib`, 555,638 bytes, SHA-256 `cd6162b0…382b90` |
| **Test metrics** (untouched test set) | XGBoost: ROC-AUC **0.7831**, PR-AUC 0.5817, Brier 0.1311, precision 0.5224, recall 0.5970, F1 0.5572. Logistic regression: ROC-AUC 0.7603. "Delayed last month" rule: ROC-AUC 0.6972. CV ROC-AUC 0.7765 ± 0.0096. |
| **Output** | Probability of a missed payment next month for each card, a risk band, and the top SHAP contributions, each labelled "raises risk" or "lowers risk". |
| **Limitations** | Learned from Taiwanese card customers in 2005. It is a behaviour-based default-risk pattern, **not an Indian credit-bureau score**, and its accuracy for Indian borrowers is not established. |

## 2. Peer Benchmarking: K-Means

| | |
|---|---|
| **Implementation** | `backend/app/ml/peers.py` · `analysis.ml.peers` |
| **Input features (8)** | Liquid savings (months of income); debt / yearly income; debt payments / income; card balance / yearly income; net worth / yearly income; financial assets / all assets; equity / financial assets; saved last year. All are standardised. |
| **Dataset** | Survey of Consumer Finances 2022 summary extract, Board of Governors of the Federal Reserve System. 22,975 records (4,595 families × 5 implicates); 197 records without positive income were excluded, leaving 22,778. United States. Survey year 2022 (income refers to 2021). |
| **Training** | `python -m app.ml.train peers`. K-Means on the stacked implicates, weighted by the survey weight `WGT`. k is chosen by the highest silhouette (k = 3), and stability is measured by the adjusted Rand index across implicates. Trained in 2.3 s. |
| **Artefact** | `real/peers/v20261114-215812/model.joblib`, SHA-256 `46f62c7a…c816` |
| **Metrics** | Minimum cross-implicate ARI **0.8669** (criterion ≥ 0.70); silhouette **0.2187** (criterion > 0); weighted shares sum to 100%. Groups include "Thin cushion, not saving" (37.7% of households) and "Borrowing to own". |
| **Output** | The user's peer group and, for each ratio, "better than X% of people" with the peer-group and population medians. Needs at least 3 months of income and spending, otherwise it says so. |
| **Limitations** | US households, not Indian. Household-level data, while a Finora profile may be one person. The 2022 summary extract has no spending, so the groups describe savings, debt and assets, not spending habits. |

## 3. Transaction Categoriser: TF-IDF + logistic regression

| | |
|---|---|
| **Implementation** | `backend/app/ml/categoriser.py` · `POST /api/categorise` · applied on manual entry and statement import; suggestions are accepted or corrected through `POST /profiles/{id}/transactions/{tx}/suggestion` |
| **Input** | The narration text. Character 2–5-grams plus word n-grams, with digits collapsed. Six bank-side categories (Rent, EMI, Investment, Transfer, Card Payment, Cash) are **rules**, not the model. |
| **Datasets** | (a) State of Oklahoma Purchase Card FY2021–FY2024, data.ok.gov, CC BY, 1,548,316 records: training and held-out-merchant test. (b) District of Columbia Purchase Card Transactions, Open Data DC, CC BY 4.0, 647,494 records: independent test. (c) MoneyVis (UK personal account, CC BY 4.0): independent test with people-assigned categories. |
| **Training** | `python -m app.ml.train categoriser`. 45,477 rows from 32,065 merchant groups (at most 40 per merchant). Merchants are split so that no merchant appears in both training and test. Logistic regression C = 8. The deployed model was refitted on all Oklahoma groups after evaluation. 55.3 s, 852.4 MB. |
| **Artefact** | `real/categoriser/v20261114-222418/model.joblib`, 9,659,567 bytes, SHA-256 `ff36635a…6d31` |
| **Metrics** | Held-out merchants (Oklahoma, 8,822 rows): macro-F1 **0.5998**, accuracy 0.7888 (keyword rules: 0.1494 / 0.4384). DC independent test (36,395 rows): macro-F1 **0.5851**, accuracy 0.8475. MoneyVis UK personal (602 rows): macro-F1 **0.3815**, accuracy 0.6329. Leakage check: 0 shared merchant groups. |
| **Output** | Category, confidence (0–1) and the n-grams that drove it. Confidence below 0.5 is marked `needs_review` and goes to the Review queue rather than being applied silently. |
| **Observed in Phase 9** | `UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Payment` → **Shopping, confidence 0.468**, marked for review (the keyword rule would have said Dining). This is the documented gap: the model learned US institutional descriptors. |
| **Limitations** | Accuracy on Indian UPI/NEFT narrations is **not measured**, because no real labelled Indian data is publicly available. Personal categories such as Subscriptions may be under-represented. |

## 4. Anomaly Detection Scanner: Isolation Forest

| | |
|---|---|
| **Implementation** | `backend/app/ml/anomaly.py` · `analysis.ml.anomaly` · review workspace `/models/review` (`/api/models/anomaly-review`) |
| **Input features (5, per person)** | Amount relative to the person's category median (`ratio_to_cat_median`); robust z-score; share of the month's category spend; ratio to the person's 95th percentile; same-day same-category count. All are relative to **the person's own history**. |
| **Dataset** | State of Oklahoma Purchase Card FY2021–FY2024 (CC BY). Training uses FY21–23: 1,053,741 transactions from 5,348 cardholders. The chronological test uses FY24: 373,602 transactions. |
| **Training** | `python -m app.ml.train anomaly`. Isolation Forest, 300 trees, contamination 0.015. 89.6 s, 913.9 MB. |
| **Artefact** | `real/anomaly/v20261114-222608/model.joblib`, 2,589,927 bytes, SHA-256 `e23b30dd…a276a`; `review_sample.json` (300 items) |
| **Metrics** | FY24 flag rate **1.41%** (target 1.5% ± 2 points). Flag-set stability across seeds (Jaccard): **0.868 / 0.916 / 0.823**, criterion ≥ 0.70. **Accuracy: not measured.** The data has no unusualness labels, and the blinded human review of 300 items is prepared but has not been completed by reviewers. |
| **Output** | Flagged transactions with an anomaly score, the typical amount and human-readable reasons, e.g. "₹18,293 is 41.3× your typical Dining transaction (median ₹443)". |
| **Separate research benchmark** | `real/anomaly_ulb_benchmark/` is a method benchmark on the ULB/Worldline card-fraud dataset (September 2013, 284,807 rows, 492 frauds; labels not used for training). On day 2: ROC-AUC 0.9606, PR-AUC 0.1301, precision 0.0616 at recall 0.654. It is **not** the deployed scanner and is not used by Finora. |
| **Limitations** | Unsupervised: "unusual" does not mean fraudulent. Institutional card spending differs from personal spending. Agreement with human judgement is unknown until the blinded review is done. |

## 5. Cash-Flow Forecast: XGBoost

| | |
|---|---|
| **Implementation** | `backend/app/ml/forecast.py` · `analysis.ml.forecast` · Future → Cash flow |
| **Input features (9)** | Last month vs 6-month average; two months ago vs 6-month average; last 3 months vs 6-month average; 12-month average vs 6-month average; typical (median) month vs average; recent spending trend; spending variability; income vs spending; transaction-count trend. Target: next month / trailing 6-month mean. |
| **Dataset** | MoneyVis Bank Transactions Dataset, R. S. Laramee, University of Nottingham (Mendeley Data, DOI 10.17632/dnxtg6n4rv.1), CC BY 4.0. 6,567 transactions from one real UK person, 2015-07-27 to 2022-07-25. |
| **Training** | `python -m app.ml.train forecast`. Rolling-origin chronological evaluation: each of 47 test months (2018-08 to 2022-06) is predicted by a model trained only on earlier months. 5.1 s. |
| **Artefact** | `real/forecast/v20261114-215913/model.joblib`, 284,693 bytes, SHA-256 `e84f1f62…5d896` |
| **Metrics** (GBP, the dataset's currency) | XGBoost MAE **856.93**, RMSE 1,213.35. 3-month moving average MAE **809.49**, RMSE 1,142.74. Last month MAE 1,135.20. **The model does not beat the 3-month average** (−5.9%), so the acceptance criterion is not met. |
| **Output** | Next month's predicted spending with a range from held-out errors (about 80%), shown beside the 3-month average, last month's actual and the projected surplus. With no transaction history it returns `available: false` ("Needs transaction history to forecast spending"). |
| **Limitations** | One person's history (about 70 usable months) cannot show that the model works for other people. Category-level forecasts are not trained on real data and are not shown. A multi-person stage (Berka/PKDD'99) is waiting on the data owner's permission. |

## 6. Model Lab and provenance

| | |
|---|---|
| **Implementation** | `backend/app/ml/provenance.py`, `registry.py`, `acceptance.py` · `GET /api/models/lab`, `GET /api/models/metrics` · `frontend/src/pages/ModelLab.jsx` (`/models?tab=lab`, deep link `?model=`) |
| **What it shows** | For each model: the live version and its checksum; activation history and reasons; dataset name, publisher, source URL, licence, geography and period; training command, duration and memory; the evaluation metrics above; the predefined acceptance checks with pass/fail; scope statements. |
| **Integrity** | Artefacts are loaded only if their SHA-256 matches `active.json`. Retraining through the API is disabled (`POST /api/models/retrain` returns 410); training is a local command-line step. |
| **Review workspace** | `/models/review` collects blinded labels for the anomaly sample. Each label belongs to the signed-in account (`PUT /api/models/anomaly-review/{item}`). `python -m app.ml.real.anomaly_review_eval` computes precision once enough labels exist. |

## The local language model (not trained by Finora)

The AI CFO uses **Qwen 2.5 3B Instruct** (`qwen2.5:3b`) through a local Ollama server. Finora does not train or fine-tune it. Remote and cloud models are refused by `app/cfo/llm.py`. Its evaluation is in [PHASE_7_VERIFICATION.md](PHASE_7_VERIFICATION.md); Phase 9's targeted live check is in [PHASE_9_VERIFICATION.md](PHASE_9_VERIFICATION.md).

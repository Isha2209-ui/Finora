# Finora Phase 6: data and model audit (before any training)

Prepared 15 Nov 2026 on branch `phase-6-models` (from `master` at `26b5a83`).
- **Nothing downloaded or trained:** no dataset has been downloaded and nothing has been trained. Only a few header lines and metadata were read to verify the sources, and those reads are cited below.
- **Waiting for approval:** training waits for your approval of the datasets and the method.

## A. Existing model inventory

| Model | Algorithm (as specified?) | Code | Artifact (SHA-256 prefix) | Training data actually used |
|---|---|---|---|---|
| Credit risk | `XGBClassifier` + SHAP `TreeExplainer`; logistic regression baseline. **As specified.** | `app/ml/credit_risk.py` | `artifacts/credit_risk.joblib` (`e8d7e42804fa`) | `datasets/uci_credit_card_default.csv` (30,000 rows, SHA-256 `a0f0ab49d632…`). Real data. |
| Transaction categoriser | TF-IDF (char 2–5 + words) + `LogisticRegression`. **As specified.** | `app/ml/categoriser.py` | `artifacts/categoriser.joblib` (`d7e83205fae8`) | 9,436 narrations **generated** by `app/data/narrations.py` templates. **Synthetic.** |
| Anomaly detector | `IsolationForest` (300 trees). **As specified.** | `app/ml/anomaly.py` | `artifacts/anomaly.joblib` (`f50a3b3dc866`) | Transactions of the **240-person generated population**, with **planted** anomaly labels. **Synthetic.** |
| Cash-flow forecaster | `XGBRegressor`; 3-month moving-average baseline. **As specified.** | `app/ml/forecast.py` | `artifacts/forecast.joblib` (`3138fb1494c0`) | 12-month histories of the generated population. **Synthetic.** |
| Peer benchmarking | `KMeans` (k chosen by silhouette). Optional, and already part of the original implementation. | `app/ml/peers.py` | `artifacts/peers.joblib` (`7c5a57139783`) | The generated population. **Synthetic.** |
| AI CFO | Pretrained LLM via Ollama + backend calculator tools. Not trained by Finora. | `app/cfo/` | n/a | n/a |

**Metrics file.** `artifacts/metrics.json` says `trained_at 2026-11-13T18:19:27Z`. No machine, environment, dataset checksum or artifact checksum was recorded.

## B. Real versus synthetic training data
- **Real:** credit risk (UCI, real anonymised customers).
- **Synthetic, so not acceptable as final models under this specification:**
  - the categoriser (generated narrations);
  - the anomaly detector (generated population, planted anomalies);
  - the forecaster (generated histories);
  - peers (generated population).

## C. Unknown provenance
- **No artifact has verifiable training provenance.** All five were saved on 13 Nov 2026 with no record of the machine, Python and library versions, the command, or a dataset checksum. They cannot be called "trained locally" without retraining.
- **The local UCI CSV is a converted copy.** The original UCI file is `.xls`; who converted it, when, and with what changes is unrecorded. It will be re-downloaded from UCI and compared value by value before use.
- **The AI CFO is not configured as specified.** `.env` and the code default select `qwen3.5:4b`, not Qwen 2.5. `qwen2.5:3b` is installed in Ollama (1.9 GB). Switching the model and verifying it is Phase 7 work; Phase 6 only records its provenance.

## D/E. Proposed real datasets, verified at the source

| # | Dataset | Publisher, source | Licence (as stated by the publisher) | Real? | What it supports |
|---|---|---|---|---|---|
| 1 | **Default of Credit Card Clients** (Yeh & Lien 2009). Taiwan, Apr–Sep 2005, 30,000 cardholders, 23 variables, target `default payment next month` | UCI ML Repository, https://archive.ics.uci.edu/dataset/350, DOI 10.24432/C55S3H | **CC BY 4.0** | Real, anonymised | Credit risk. Fully suitable for the method; **not representative of Indian borrowers or Indian bureau data**. |
| 2 | **State of Oklahoma Purchase Card (PCard) transactions**, FY2021–FY2024 (monthly CSVs, about 5–9 MB each) | Oklahoma Office of Management and Enterprise Services, https://data.ok.gov (`purchase-card-pcard-fiscal-year-2024`, `-2023`, `pcard-fy-2022`, `state-of-oklahoma-purchase-card-pcard-fy-2021`) | **Creative Commons Attribution** on these four years. Other years have **no licence stated**, so they will not be used. | Real card transactions | Columns verified from the file: `AGENCYNAME, LAST_NAME, FIRST_INITIAL, ITEM_DESCR, AMOUNT, MERCHANT, TRANSACTION_DATE, POST_DATE, MCC_DESCRIPTION`. Real merchant descriptors (e.g. `CHICK-FIL-A #01973`, `AMZN Mktp US I01C13273`) with the card network's merchant category: **categoriser** (text → category) and **anomaly detector** (per-cardholder histories). |
| 3 | **District of Columbia Purchase Card Transactions** (2009 onwards, monthly updates) | DC Government, https://opendata.dc.gov/datasets/purchase-card-transactions | **CC BY 4.0** | Real card transactions | Columns verified from the file: `AGENCY, TRANSACTION_DATE, TRANSACTION_AMOUNT, VENDOR_NAME, VENDOR_STATE_PROVINCE, MCC_DESCRIPTION`. A **fully independent second publisher**, used only as the unseen-source test for the categoriser. |
| 4 | **Credit Card Fraud Detection** (ULB Machine Learning Group with Worldline). European cardholders, two days in Sep 2013, 284,807 transactions, 492 genuine frauds. Features `Time, Amount, V1–V28 (PCA)` | OpenML dataset 1597 (MD5 `178bcf9bb1f31a3dfe12d0e577884add`, 151 MB). Cite Dal Pozzolo et al., CIDM 2015 | OpenML licence field: **"Public"**. The Kaggle page could not be read; it is usually listed as ODbL. | Real transactions; **fraud labels are real** (investigated cases), not planted | **Anomaly method benchmark only.** The PCA features cannot be computed for Finora users, so this cannot train the production model. |
| 5 | **PKDD'99 Financial (Berka)**. A Czech bank, about 1993–1998: 4,500 accounts, about 1.06 M transactions with balances, 682 loans, 8 tables | Prague University of Economics PKDD'99 Discovery Challenge (archived), mirrored by the CTU Relational Repository (marked "Type: Real") | **No licence stated** by the publisher or CTU. Released openly for a research challenge. A Kaggle mirror labels it CC0, but that is the uploader's claim. | Real, anonymised | The **only real, longitudinal, personal bank-account dataset found**, with monthly income, spending and balances per account: **cash-flow forecaster** and **peer clusters**. |

**Rejected after checking:**
- **Synthetic data:** PaySim, the Sparkov "credit card transactions", Hugging Face `us-bank-transaction-categories` (stated as synthetic), and the GoMask/marketplace transaction sets.
- **Unverifiable origin:** the Kaggle "Indian Banking Transaction Text Dataset" and the GitHub "259k Open Banking transactions" (provenance not verifiable).
- **Licence restrictions:** IEEE-CIS (Vesta) fraud data (competition-only terms).
- **Not public:** the Brazilian bank sets in arXiv 2312.07730.

**India:** I found **no publicly licensed, real, labelled dataset of Indian bank or UPI transaction descriptions across multiple banks**. The categoriser therefore cannot be trained or tested on real Indian narrations, and this is stated plainly.

## F. Local resources (MacBook Air M2, 8 GB RAM, 32 GB free disk)

| Dataset | Download | Disk (raw + processed) | Peak memory (estimated) | Training time (estimated) |
|---|---|---|---|---|
| UCI credit | about 5 MB | < 20 MB | < 0.5 GB | < 1 min (5-fold CV + SHAP about 1–2 min) |
| Oklahoma FY2021–24 | 48 files, about 330 MB | about 0.7 GB | about 2–3 GB (read in chunks, only the columns needed) | categoriser 5–15 min; Isolation Forest 1–3 min |
| DC | one CSV, size not yet known (estimated 100–300 MB) | about 0.5 GB | about 1–2 GB | test only |
| ULB | 151 MB | about 0.3 GB | about 1.5 GB | about 1 min |
| Berka (if approved) | about 17.5 MB zipped | about 0.2 GB | < 1 GB | forecaster < 2 min; K-Means seconds |

**Totals:** about 1.5–2 GB of disk, under 4 GB peak memory, well under an hour of training. Everything runs locally on the CPU; XGBoost and scikit-learn do not use MPS.

## G. Method per model (only if approved)

**Common to all models:**
- Raw files are kept **unchanged** in `backend/datasets/raw/` (git-ignored), with a SHA-256 checksum and the source URL.
- Cleaning is done by scripts in `app/ml/data/` into `backend/datasets/processed/`.
- Each run writes `artifacts/<version>/` with the model, a metrics JSON and a provenance JSON: all 20 fields you listed, plus the Mac, OS, Python and library versions, the command, start/end time and duration, peak memory, and the dataset and artifact checksums.
- The current artifacts are moved to `artifacts/legacy-synthetic-2026-11-13/` and **not deleted**. A new artifact replaces an old one only after it passes evaluation, and rollback is a configuration switch.
- `python -m app.ml.train` trains only the approved models. A blocked model is reported as BLOCKED and never silently skipped or filled in.

1. **Credit risk** (unchanged architecture)
   - **Provenance check:** re-download the UCI file and confirm the local CSV matches it value for value.
   - **Data:** demographics stay excluded. The money features become ratios to the credit limit, as now. The codes −2/−1/0 are documented (no missing values in the source); duplicates are checked.
   - **Split:** stratified 70/15/15 train/validation/test, plus 5-fold stratified cross-validation on the training part.
   - **Metrics:** ROC-AUC, PR-AUC, precision, recall, F1, confusion matrix at the validation-chosen threshold, and Brier score.
   - **Comparisons and explanation:** compared against logistic regression and a "delayed last month" rule; SHAP global importance plus per-person explanations.
   - **Stated limit:** Taiwan 2005; not evidence of accuracy for Indian borrowers.
2. **Categoriser** (unchanged architecture)
   - **Data:**
     - text is the real `MERCHANT`/`VENDOR_NAME` descriptor;
     - the label is `MCC_DESCRIPTION` mapped to Finora categories by a **published mapping table** (for example "Fast food restaurants" → Dining, "Grocery stores, supermarkets" → Groceries, "Service stations" → Fuel, "Airlines" and "Lodging" → Travel, "Drug stores" → Health, "Telecommunication services" → Utilities);
     - MCC groups with no personal-finance meaning (industrial supplies, government services and similar) are **excluded** and counted, never forced into a category.
   - **Leakage control:** the split is **grouped by normalised merchant**, so no merchant appears in both training and test.
   - **Metrics:** macro-F1, per-class precision and recall, and confusion matrix, compared against the existing keyword rule.
   - **Generalisation test:** trained on Oklahoma, tested on **DC**, an independent publisher with a different descriptor style.
   - **Stated limits:**
     - these are US institutional purchase-card descriptors, not Indian UPI/NEFT narrations, so accuracy on Indian statements is **unmeasured**;
     - Rent, EMI, Investment, Transfer, Card Payment and Cash have **no real labelled source** (they are bank-side transaction types, not merchant categories) and cannot be learned by this model.
3. **Anomaly detector** (unchanged architecture)
   - **Training data:** Isolation Forest on real Oklahoma cardholder histories. The cardholder is a salted hash of agency + name; **names are dropped at ingestion**.
   - **Features:** the same person-relative features as now (ratio to own category median, robust z, share of month, ratio to own p95, repeat count, size).
   - **No labels in this data:** precision and recall **cannot be measured** on it and will not be claimed. Instead, flag rates and how stable they are across years.
   - **Method benchmark on ULB:** Isolation Forest trained on legitimate transactions, evaluated on the 492 real frauds. Precision, recall, F1 and false-positive rate at fixed flag rates, against a rule baseline (amount above the 99th percentile).
   - **Stated limit:** "unusual", never "fraud"; the benchmark validates the method, not the deployed model.
4. **Cash-flow forecaster** (unchanged architecture; **needs Berka**)
   - **Data:** monthly outflow per account from real transactions; months without transactions count as genuine zero-activity months; accounts with fewer than 18 months are excluded and counted.
   - **Features and split:** lag features only (no future data). The split is chronological: train to 1997-06, validate 1997-07 to 1997-12, test 1998.
   - **Metrics:** MAE and RMSE against the 3-month moving average and last-month baselines, with actual versus predicted per month.
   - **Stated limit:** Czech koruna, 1990s, not Indian households.
5. **Peers (K-Means)** (unchanged; optional; **needs Berka**)
   - **Data:** behaviour features per account (savings rate, spending variability, income variability, share of household and loan payments), from real transactions.
   - **Method:** k by silhouette; stability by adjusted Rand index across bootstrap samples.
   - **Stated limit:** cohorts are Czech accounts from the 1990s.
6. **AI CFO (Qwen 2.5 via Ollama).** No training or fine-tuning.
   - **Phase 6:** record the model's provenance (publisher Alibaba Qwen team, Ollama tag, digest `357c53fb659c` for `qwen2.5:3b`, its licence as published for that size, quantisation).
   - **Phase 7:** switch the configuration from `qwen3.5:4b` to Qwen 2.5 and verify the number-checking.

## H. Models that cannot responsibly be completed as specified
- **Cash-flow forecaster and peers:** the only real longitudinal personal bank data found (Berka) has **no stated licence**. Unless you accept using it on the basis of its open research release, both are **BLOCKED**. I will not substitute the institutional purchase-card spending as if it were household cash flow.
- **Categoriser on Indian narrations:** no real Indian labelled data exists publicly. The model can be trained on real data (US card descriptors), but its accuracy on Indian statements stays **unmeasured**. Bank-side categories (Rent, EMI, Investment, Transfer, Card Payment, Cash) cannot be learned from any real source found.
- **Anomaly detector against real fraud:** the deployable model can be trained on real transactions, but no real-labelled dataset shares its features. Detection quality is shown only as a method benchmark on ULB.

## Decisions needed before training
1. Approve UCI (CC BY 4.0) for credit risk (verify, then retrain locally).
2. Approve Oklahoma FY2021–24 (CC BY) to train, and DC (CC BY 4.0) to test, the categoriser. Also decide what Finora does with the six bank-side categories the real-data model cannot learn:
   - (a) the existing Phase 4 structural rules handle them, with rules added only for those six and labelled as rules, not ML;
   - (b) they are left unclassified until you review them.
3. Approve Oklahoma (CC BY) to train, and ULB ("Public" on OpenML) to benchmark, the anomaly detector.
4. Berka (real, licence unstated): **approve** for the forecaster and peers, or mark both **BLOCKED**.
5. Confirm the old synthetic artifacts may be moved, not deleted, to a legacy folder and switched off in favour of the approved models.

## Sources checked
- UCI dataset 350: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
- Oklahoma PCard FY2024: https://data.ok.gov/dataset/purchase-card-pcard-fiscal-year-2024 (licence via the CKAN API `package_search`)
- DC catalog: https://catalog.data.gov/dataset/purchase-card-transactions (CC BY 4.0); file header from `opendata.dc.gov` download
- OpenML 1597: https://www.openml.org/api/v1/json/data/1597
- CTU Financial: https://relational.fel.cvut.cz/dataset/Financial; PKDD'99 challenge page (archived): https://web.archive.org/web/20180506061559/http://lisp.vse.cz/pkdd99/Challenge/chall.htm
- Rejected: arXiv 2312.07730, Hugging Face `DoDataThings/us-bank-transaction-categories`, Kaggle "Indian Banking Transaction Text Dataset"

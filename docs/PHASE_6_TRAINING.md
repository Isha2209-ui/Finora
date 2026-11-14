# Phase 6: real-data training report

Branch `phase-6-models`. Every model below was trained **locally** on the owner's MacBook Air M2 (8 GB, CPU only;
XGBoost and scikit-learn do not use the Apple GPU here). No cloud service, no Colab, no Kaggle. **No synthetic observation
was used at any stage.** Each run writes `backend/artifacts/real/<model>/<version>/` containing `model.joblib`,
`metrics.json` and `provenance.json` (datasets with file SHA-256s, licence, period, cleaning, environment, library versions,
timings, peak memory and artifact SHA-256).

## How models reach the app

1. **Train and evaluate.** `python -m app.ml.train <model> --approved` does both and never activates anything.
2. **Check acceptance criteria.** Each model has predefined criteria in `app/ml/acceptance.py`; `python -m app.ml.train check` runs them on every trained version. The criteria come from the approved plan: beat the stated baseline and pass the stability checks. The categoriser and anomaly criteria were written **before** their final runs.
3. **Activate.** `python -m app.ml.train activate <model> <version> --reason "..."` refuses a version unless all of these hold:
   - the provenance says `data_status: real`, `evaluation_passed` and `approved_by_owner`;
   - the artifact still matches its SHA-256;
   - the version is not a benchmark;
   - its recorded metrics pass the acceptance criteria, **re-computed at activation** rather than trusted from a flag.
4. **Deactivate or roll back.** `deactivate` and `rollback` keep every change in `active.json["_history"]`. Writes to `active.json` are atomic.
5. **Loading.** The registry loads only the versions listed in `active.json`, re-checking each checksum. A model without one is reported as `available: false, model_status: awaiting_approved_model`: in the analysis, on the pages, in the PDF report and in chat. Nothing is trained automatically, and nothing falls back to a synthetic model.
6. **Legacy models.** The five legacy synthetic-trained artifacts and their `metrics.json` were moved with `git mv`, byte-identical (checksums in the folder's README), to `artifacts/legacy-synthetic-2026-11-13/`. **Nothing was deleted.** They load only with `MODEL_SET=legacy-synthetic`.
7. **No API training.** `POST /api/models/retrain` returns 410.

## Results

### 1. Credit risk: UCI Taiwan 2005. Active, `v20261114-211415` (passes all 3 criteria; verified 2026-11-15, not retrained)

| | XGBoost | Logistic regression | Rule: "late last month" |
|---|---|---|---|
| Test ROC-AUC | **0.7831** | 0.7603 | 0.6972 |
| Test PR-AUC | 0.5817 | 0.5347 | 0.3820 |
| F1 at the validation-chosen threshold | 0.5572 (t = 0.26) | 0.5366 | 0.5277 |
| 5-fold CV ROC-AUC (training part) | 0.7765 ± 0.0096 | 0.7548 ± 0.0104 | |

- **Split:** stratified 70/15/15, giving 21,000 / 4,500 / 4,500 rows (`random_state` 7). The threshold maximises F1 on validation only.
- **Test confusion matrix:** TN 2,962 · FP 543 · FN 401 · TP 594.
- **Data:** the local CSV is a cell-for-cell copy of the official UCI `.xls`; 750,000 of 750,000 cells are identical.
  - 35 duplicate rows (excluding ID) are kept and disclosed.
  - 1,930 rows have a negative bill. A negative bill is a credit balance, so utilisation uses max(0, bill).
  - Undocumented codes appear in EDUCATION (0, 5, 6) and MARRIAGE (0). They have no effect, because SEX, EDUCATION and MARRIAGE are not model inputs.
- **Duplicate and negative-bill verification** (`verification.json` next to the model):
  - The 35 duplicates are 35 exact pairs. 60 of their 70 rows are dormant accounts with zero bills and payments, and no pair has conflicting labels.
  - 12 test rows have a duplicate outside the test set. Excluding them gives a test ROC-AUC of 0.7836, against 0.7831 reported.
  - Excluding the 142 test rows whose engineered features also occur in training gives 0.7824.
  - So duplicates do not inflate the result. Nothing was removed.
  - Negative bills: 590 in the latest month (`BILL_AMT1`), 3,932 cells, 1,930 rows. They are credit balances: utilisation uses max(0, bill), a repayment ratio whose previous bill is ≤ 0 is 1.0, and ratios are capped at 2.0.
  - 0 rows were removed.
- **Explanations:** SHAP TreeExplainer.
- **Run:** 3.0 s, 219.5 MB peak.
- **Label:** a Taiwan 2005 benchmark, not an Indian credit-bureau score.

### 2. Spending forecast: MoneyVis. **Available as EXPERIMENTAL** (fails its acceptance criterion; shown next to the baseline). `v20261114-215913`

- **Data:** one real UK current account, 2015-07-27 to 2022-07-25, with 6,567 transactions and 83 whole months.
  - The two partial months are dropped.
  - 2,816 Excel serial dates are corrected by a day/month swap. The swap is proven: 0 date-order violations with it, 149 without.
  - Original observations are preserved under `datasets/raw/`. Processed files are written separately.
- **Evaluation:** rolling-origin and chronological. Each of 47 test months (2018-08 to 2022-06) is predicted by a model trained only on earlier months.

| | MAE (£) | RMSE (£) |
|---|---|---|
| XGBoost | 856.93 | 1,213.35 |
| 3-month moving average | **809.49** | **1,142.74** |
| Same as last month | 1,135.20 | 1,558.18 |

- **The model does not beat the 3-month moving average** (MAE −5.9%). Nothing was tuned on the test months to change it.
- Its predefined acceptance criterion is "MAE below the 3-month moving average", so per the owner's instruction (2026-11-15) it was **deactivated** and is not used.
  - The Forecast page and the PDF report say no approved forecasting model exists and why.
  - Model Lab shows it as experimental, with its failed criterion.
- The trainer now sets `evaluation_passed` from that criterion.
  - A deterministic retrain (`v20261114-215913`) reproduced every number and every prediction of `v20261114-211601` exactly.
  - Only its provenance flag differs: now `false`.
  - Both versions are kept.
- **Search for multi-person data (2026-11-15).** Nothing found is real, multi-person, retail and openly licensed:
  - Multimodal Banking Dataset: CC BY-NC-ND, and its clients are corporate.
  - Kaggle "retail banking" sets: synthetic, or the licence is unclear.
  - Berka (PKDD'99): publicly reachable, but no licence statement was found, so it stays on hold pending the permission request (Appendix A of the acquisition report).
- Category-level forecasts have no real training data and are not shown.
- **Run:** 4.4 s, 216.9 MB peak.

### 3. Peer groups: Federal Reserve SCF 2022. Active, `v20261114-215812` (verified 2026-11-15)

- **Data:** 22,975 records, which is 4,595 families × 5 implicates; every family has exactly 5.
  - 197 records without positive income are excluded. That removes 36 families entirely and 6 families from some implicates, 0.39% of the weight.
  - 4,559 families remain.
  - `TOTSPENDNH` is zero on every record of the public summary extract, so spending is not used.
- **Weights, a correction found by verification.** In the public extract, each implicate's `WGT` already sums to 26.26 million, which is 1/5 of the ~131 million US families. Stacking the 5 implicates therefore uses `WGT` itself, giving a stacked total of **130.8 million: every household counted once**.
  - The first version divided by 5 again, a total of 26.2 million. Because that scaled every weight equally, clusters, weighted medians, shares and percentiles were unaffected: the retrained model gives **identical cluster labels for every record**.
  - The code and documentation are corrected, and the corrected version is active.
- **Sizes are households, never records.**
  - Profile comparisons now report the group's weighted share of US households and its size in millions of households. The old `peer_group_size` counted stacked records, 5 per household, and was removed.
  - A group's `families` field counts families with at least one implicate in that group. A family split across groups appears in more than one, so these counts are not meant to be summed; the weighted shares sum to 100%.
- **Stability:**
  - 91.6% of families (89.9% of the weight) fall in the same group in all their implicates.
  - ARI against the stacked model per implicate: 0.957–0.993.
  - ARI between implicates: mean 0.878, minimum 0.867.
- **Fit:** k = 3 by silhouette, giving silhouette 0.219 and Davies-Bouldin 1.575: weak but real structure.
- **Values:**
  - No missing values; the Fed imputes them.
  - Clipped values: liquid months 1.6%, debt/income 1.0%, net worth/income 3.2%, others ≤ 0.5%. Three heavy-tailed ratios are signed-log transformed.
  - Common zeros: card balance 62%, equity share 37%, saved last year 38.5%, debt 27%.
- **Groups**, named from weighted medians in natural units:

| Group | Share of US households | Median liquid savings | Debt / income | Net worth / income |
|---|---|---|---|---|
| Thin cushion, not saving | 37.7% | 0.4 months | 0.10 | 0.45 |
| Borrowing to own | 27.2% | 0.9 months | 2.35 | 2.47 |
| Wealthy investors | 35.1% | 4.9 months | 0.21 | 6.94 |

- **Finora's eight ratios, aligned with the SCF definitions:**
  - Liquid savings uses bank balances only; SCF `LIQ` has no FDs and no cash in hand.
  - Financial assets are bank + FDs + equity + mutual funds + retirement + bonds; SCF `FIN` excludes gold, cash, property and crypto.
  - "Saved" means the last 12 months, not the whole history.
- **Differences that remain, shown to the user:**
  - SCF income is gross; Finora sees take-home pay, so Finora's ratios to income read higher.
  - Card balance is the current outstanding amount, not the balance after payment.
- **Not Indian:** these are US household comparisons, not Indian individual benchmarks, and every output says so.
- **Removed run:** `v20261114-212535`, an unactivated run made minutes earlier during the naming fix, was removed. All other versions are kept.

### 4. Categoriser: Oklahoma FY2021–24, tested on DC and MoneyVis. Active in **suggestion-only** mode, `v20261114-222418`

**Data.**
- **Oklahoma:**
  - 48 monthly files covering 48 calendar months, July 2020 to June 2024, each month in exactly one file.
  - No row appears in two files. The timestamped file names are publication names, not republished copies.
  - 1,548,316 rows, of which 0 are invalid and 0 duplicated across files. Rows per fiscal year: FY21 335,640, FY22 382,724, FY23 408,063, FY24 421,889.
  - Every file's SHA-256 is in `SOURCE.json` and re-verified after download.
  - Two acquisition defects were found and fixed:
    - The publisher served February and March 2022 under one file name. The March file is now kept as `pcard-fy-2022__507c08f1__pcard_public_202203.csv`; without the fix, March 2022 would have been lost.
    - Two files (August and September 2023) have no `ROWID` column, and the loader no longer needs it.
- **Labels:** the card network's MCC description, mapped by the explicit rules in `app/ml/data/pcard.py`.
  - 209 of 548 MCC descriptions (559,432 rows) are **excluded**, never forced into a category: industrial, government, B2B, fees and other codes with no personal-finance meaning.
  - The full mapping actually applied is in `datasets/processed/pcard/mcc_mapping.csv`.
- **Training set:** 45,477 distinct descriptors from 32,065 merchant groups, at most 40 per merchant.
- **Class distribution:** Shopping 18,318, Travel 8,709, Dining 8,150, Education 2,828, Fuel 1,643, Subscriptions 1,444, Entertainment 1,397, Groceries 1,238, Health 908, Utilities 768, Insurance 74.

**Leakage.**
- Grouped 80/20 split by merchant group: 0 groups in both train and test.
- 0 test descriptors identical to a training descriptor.
- DC overlap is reported, and DC is also scored on unseen merchants only.

| Test | Rows | Macro-F1 | Accuracy | Keyword rules (macro-F1) |
|---|---|---|---|---|
| Oklahoma, merchants never seen | 8,822 | **0.600** | 0.789 | 0.149 |
| DC purchase cards (independent) | 36,395 | 0.585 | 0.848 | 0.143 |
| DC, merchants not in Oklahoma training | 18,373 | 0.449 | 0.718 | 0.156 |
| MoneyVis UK personal account (people's labels) | 602 | 0.382 | 0.633 | 0.131 |

Per class, held-out Oklahoma:

| Category | Precision | Recall | F1 |
|---|---|---|---|
| Travel | 0.92 | 0.85 | 0.89 |
| Dining | 0.84 | 0.86 | 0.85 |
| Shopping | 0.75 | 0.92 | 0.83 |
| Fuel | 0.91 | 0.52 | 0.66 |
| Utilities | 0.82 | 0.50 | 0.62 |
| Health | 0.73 | 0.46 | 0.57 |
| Education | 0.59 | 0.52 | 0.56 |
| Entertainment | 0.59 | 0.37 | 0.46 |
| Insurance | 1.00 | 0.29 | 0.44 |
| Subscriptions | 0.79 | 0.29 | 0.43 |
| Groceries | 0.59 | 0.21 | 0.31 |

- **Error pattern:** most errors go *into* Shopping, the dominant class. The full confusion matrices are in `metrics.json`.
- **Rare category:** Insurance has 74 training descriptors and 14 held-out examples (F1 0.44). It is too rare to learn reliably.
- **Confidence (review threshold 0.5):** on held-out merchants, 90% of predictions are confident and those are 83% correct; the rest are 40% correct. On DC: 92% confident, 89% correct.

**Acceptance:** all 4 criteria passed (written before the run), so the model was activated.

**Indian-format narrations: not dependable.**
- On Finora's own Indian-format test narrations, it agreed with the intended merchant category only 30% of the time. That figure is from test fixtures, not a validation, but it is a warning.
- Even its *confident* predictions agreed only 44% of the time. Typical errors: Netflix → Utilities, and Swiggy, DMart, Uber and IOCL → Shopping.
- So it runs in **suggestion-only** mode (`categoriser.SUGGESTION_ONLY`). Every model category is a suggestion the person confirms in Review, and Model Lab and the Transactions tooltip say so.
- Bank-side categories (rules) and the person's own choices are unaffected.
- No Indian accuracy is claimed.

### 5. Anomaly Detection Scanner: Oklahoma (part A) and blinded review (part B). **Available as EXPERIMENTAL, not human-validated**, `v20261114-222608`

- **Training:** FY2021–23, 1,053,741 transactions from 5,348 cardholders with at least 20 transactions.
- **Chronological test:** FY2024, 373,602 transactions.
- **Features:** the 5 scale-free ratios of the deployed feature set.
  - `log_amount` is dropped because it depends on currency.
  - `source_rarity` is dropped because Oklahoma has one card per cardholder.
- **Flag rate:** 1.50% in training, 1.41% in FY2024.
- **Stability:** Jaccard of the flagged set against other seeds 0.868, 0.916 and 0.823.
- **Overlap with the "3× usual" rule:** 0.083. The model and the rule flag mostly different transactions.
- **Accuracy: not measured.** There are no labels. Nothing is claimed about fraud, and nothing about accuracy until people review.
- **Blinded review sample** (stored with the model as `review_sample.json`, SHA-256 in its provenance):

| Stratum | Population (FY2024) | Sampled | Selection probability |
|---|---|---|---|
| S1 flagged by the model | 5,260 | 150 | 0.0285 |
| S2 flagged by the 3× rule only | 57,550 | 75 | 0.0013 |
| S3 neither | 310,792 | 75 | 0.00024 |

- **What reviewers see.** Items are served in a fixed random order, without score, flag, stratum or selection probability; this was verified on the live API response. Reviewers see the transaction and the cardholder's own category history only.
- **Who can review and what is recorded:**
  - only full (non-guest) accounts can label;
  - each reviewer's label is stored separately;
  - agreement between reviewers is reported with Cohen's kappa.
  - Nothing is labelled automatically, and no label was entered during development.
- **Evaluation once labels exist** (`python -m app.ml.real.anomaly_review_eval`):
  - consensus labels;
  - precision of the model's flags, and the share of flags judged usual;
  - Horvitz-Thompson estimates of the false-positive rate and recall, each reported **only** if every stratum has ≥ 30 consensus labels and unusual items were found outside S1, otherwise "not estimable".
  - Labels mean *perceived unusualness*, not confirmed fraud.
- **Acceptance:**
  - flags stable across seeds (passed);
  - a completed review in which ≥ 50% of the model's flags are judged unusual (**not met: review not completed**).
  - Accepted activation is refused. On the owner's instruction (2026-11-15) it runs as **experimental**, with the unmet criterion recorded and shown on every output.

### 6. ULB fraud benchmark (part C, separate, never the deployed model's accuracy). `v20261114-214646`, not deployable

**These numbers are not the accuracy of Finora's unusual-spending detector.** ULB features are anonymised PCA components,
so this model cannot score a Finora user's transactions. The benchmark answers one question only: on real card data with
confirmed fraud labels, does an Isolation Forest with Finora's settings separate fraud from normal activity better than a
simple amount rule?

**Data acquisition.** The official OpenML ARFF could not be downloaded: its server drops the connection after a few minutes
and ignores byte ranges, so three attempts failed. The identical data was taken from Google's public mirror (the copy the
TensorFlow imbalanced-data tutorial uses). Verification:
- The mirror file's MD5 matches the mirror's published hash.
- The first 32,017 data rows are identical, value for value in all 31 columns, to the official ARFF's. That is every complete row the official download delivered before it was cut, about 11% of the data.
- The totals match the published dataset: 284,807 rows and 492 frauds.
- The remaining 89% could not be compared with the official file. This is recorded in `SOURCE.json`.

**Protocol.** The model is trained on day 1 (`Time` < 86,400 s, 144,786 transactions) **without using labels**, then tested on day 2 (140,021
transactions, 211 confirmed frauds, a base rate of 0.15%). Labels are used only to evaluate.

| Day 2 | Isolation Forest (contamination 0.015) | Rule: amount > day-1 99th percentile |
|---|---|---|
| PR-AUC | **0.130** | 0.002 |
| ROC-AUC | 0.961 | |
| Precision / recall | 0.062 / 0.654 | 0.003 / 0.019 |
| False-positive rate | 1.5% | 0.9% |
| Confusion matrix (TN / FP / FN / TP) | 137,706 / 2,104 / 73 / 138 | 138,505 / 1,305 / 207 / 4 |

On this data, unsupervised isolation separates fraud far better than a large-amount rule. Most fraud here is not
unusually large.

**False alarms, investigated.** At the 1.5% flag rate, 2,104 of 2,242 flags (94%, about 15 in 16) are legitimate
transactions. This follows from rarity, not from a defect: the fraud base rate is 0.15%, so flagging 1.5% of transactions
can be at most ~10% precise even with a perfect ranking.

| Share flagged (top-scored) | Flagged | Frauds caught | Precision | Recall | Best possible precision |
|---|---|---|---|---|---|
| 0.10% | 140 | 40 | 28.6% | 19.0% | 100% |
| 0.17% | 238 | 44 | 18.5% | 20.9% | 88.7% |
| 0.50% | 700 | 76 | 10.9% | 36.0% | 30.1% |
| 1.0% | 1,400 | 110 | 7.9% | 52.1% | 15.1% |
| 1.5% | 2,100 | 132 | 6.3% | 62.6% | 10.1% |
| 3.0% | 4,201 | 173 | 4.1% | 82.0% | 5.0% |

Recorded in `v20261114-220005` (a rerun of the same benchmark that adds this table; identical model and metrics).

## AI CFO (not trained by Finora)

- Qwen 2.5 (Alibaba Qwen team), served by Ollama. Installed tag `qwen2.5:3b`, digest `357c53fb659c`, 1.9 GB.
- **Discrepancy, shown in Model Lab and left unchanged:** the configuration selects `qwen3.5:4b`, which is not installed and is not Qwen 2.5. It is resolved in Phase 7.

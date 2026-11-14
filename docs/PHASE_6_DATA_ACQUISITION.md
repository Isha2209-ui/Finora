# Finora Phase 6: expanded data acquisition report

Prepared 15 Nov 2026 on branch `phase-6-models`. It follows `docs/PHASE_6_AUDIT.md` and your decisions of the same day.
- **What was read:** documentation, APIs, file headers and small samples only. The two small downloads are the SCF summary extract (3 MB) and the approved UCI verification (5.5 MB). Both are in a scratch folder, outside the repository.
- **Nothing trained:** no model has been trained and no large dataset downloaded.

## Summary

| Model (algorithm unchanged) | Best genuine data | Status |
|---|---|---|
| Credit risk (XGBoost + SHAP) | UCI Default of Credit Card Clients | **Verified, ready to train.** The local copy is identical to the official UCI file. |
| Categoriser (TF-IDF + logistic regression) | Oklahoma PCard FY2021–24 (train), DC PCard (independent test) | **Approved, ready to train.** Merchant-category classification only; the six bank-side categories stay rule-based (Option A). |
| Anomaly (Isolation Forest) | Oklahoma PCard (train, real per-cardholder histories). ULB fraud (method benchmark, real labels). Blinded human review (deployed-model labels) | **Methodology proposed below; needs your approval.** |
| Cash-flow forecaster (XGBoost) | **Berka/PKDD'99** (4,500 real accounts) once written permission is obtained, plus **MoneyVis** (CC BY 4.0, one real UK account over 7 years) as independent evaluation. India upgrade: **CMIE Consumer Pyramids** (paid) | **Needs the permission request sent.** MoneyVis can be used now. |
| Peers (K-Means) | **Federal Reserve SCF 2022** (4,595 real US families, public download), plus **India AIDIS 2019** (MoSPI, free registration) | **SCF is ready now.** AIDIS needs you to register. |
| AI CFO (Qwen 2.5 via Ollama) | Pretrained, not trained by Finora | Provenance to record. **Discrepancy:** configured `qwen3.5:4b`, installed `qwen2.5:3b`. Not fixed now (Phase 7). |

---

## 1. Credit risk: XGBoost + SHAP

1. **Dataset:** "Default of Credit Card Clients", I-Cheng Yeh and Che-hui Lien (2009), *Expert Systems with Applications* 36(2), 2473–2480.
2. **Source:** https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients, DOI 10.24432/C55S3H. Download: `https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip`.
3. **Schema (verified from the official file):** `ID, LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE, PAY_0, PAY_2–PAY_6, BILL_AMT1–6, PAY_AMT1–6, default payment next month`.
4. **Records:** 30,000 rows, 23 explanatory variables + ID + target.
5. **Coverage:** a Taiwanese bank's credit-card clients, April–September 2005, with the target in October 2005.
6. **Target:** default next month (1 = 6,636, 0 = 23,364; 22.1% positive).
7. **Quality** (checked on the official file):
   - official zip SHA-256 `56c885f8…`, `.xls` SHA-256 `30c6be3a…`;
   - **the local CSV is identical to the official file: 750,000 of 750,000 cells, 0 rows differing**;
   - 0 missing values;
   - 35 duplicate rows once the ID is ignored;
   - codes outside the paper's documentation (EDUCATION 0/5/6, MARRIAGE 0), in columns the model excludes;
   - 590 negative bills (credit balances).
8. **Access:** public download; **CC BY 4.0** (credit Yeh & Lien and UCI).
9. **Task fit:** yes, a supervised probability of default; the PAY codes are documented.
10. **Preprocessing and training** (architecture unchanged):
    - demographics are dropped for fairness and portability;
    - money features become ratios to the credit limit (the existing `features_from_history`);
    - the 35 duplicate rows are kept and reported, since they are distinct customers with identical values;
    - the split is stratified 70/15/15 train/validation/test, with 5-fold stratified cross-validation on the training part;
    - the existing XGBoost hyperparameters are kept, and the threshold is chosen on validation only.
11. **Evaluation:**
    - on the untouched test set: ROC-AUC, PR-AUC, precision, recall, F1, confusion matrix and Brier score;
    - CV mean ± standard deviation;
    - compared against logistic regression on the same features and a "delayed last month" rule;
    - SHAP global importance plus per-person explanations.
12. **Resources:** about 6 MB on disk, under 0.5 GB RAM, about 2 minutes including SHAP.
13. **Gap:** Taiwan 2005, so it is **not evidence of accuracy for Indian borrowers**, and this is stated in Model Lab.

## 2. Transaction categoriser: TF-IDF + logistic regression (approved)

1. **Datasets:** (a) State of Oklahoma Purchase Card, FY2021–FY2024. (b) District of Columbia Purchase Card Transactions.
2. **Sources:**
   - (a) https://data.ok.gov: `state-of-oklahoma-purchase-card-pcard-fy-2021`, `pcard-fy-2022`, `purchase-card-pcard-fiscal-year-2023`, `purchase-card-pcard-fiscal-year-2024`; monthly CSVs through the CKAN API.
   - (b) https://opendata.dc.gov/datasets/purchase-card-transactions; CSV download.
3. **Schema (verified from the files):**
   - (a) `CALENDAR_YEAR, CALENDAR_MONTH, AGENCYNBR, AGENCYNAME, LAST_NAME, FIRST_INITIAL, ITEM_DESCR, AMOUNT, MERCHANT, TRANSACTION_DATE, POST_DATE, MCC_DESCRIPTION, ROWID`.
   - (b) `AGENCY, TRANSACTION_DATE, TRANSACTION_AMOUNT, VENDOR_NAME, VENDOR_STATE_PROVINCE, MCC_DESCRIPTION, DCS_LAST_MOD_DTTM, OBJECTID`.
4. **Records:**
   - (a) 48 monthly files of 5–9 MB each (FY2024 measured: 5.2–8.9 MB); estimated 1.5–2.5 M rows, to be counted on download.
   - (b) row count to be measured.
5. **Coverage:** (a) Jul 2020 – Jun 2024. (b) 2009 to present.
6. **Labels:** `MCC_DESCRIPTION`, the merchant category assigned by the card network and acquirer, not by Finora or a person.
7. **Quality and fit:**
   - the descriptors are genuine (`CHICK-FIL-A #01973`, `AMZN Mktp US …`, `WAL-MART #0137`, `STAPLES 00102186`);
   - this is **institutional** spending, so many categories (industrial supplies, government services) have no personal-finance meaning.
8. **Access:** public downloads; (a) **CC BY** (only the four years that declare it), (b) **CC BY 4.0**.
9. **Task fit:** **merchant-category classification**. It is not validated Indian bank-statement categorisation, and this is stated in the UI and docs.
10. **Preprocessing and training:**
    - text = the merchant descriptor, with the normaliser unchanged (digits collapsed);
    - label = MCC description mapped to Finora's merchant categories by a **published table** in `app/ml/data/mcc_map.csv`;
    - MCC groups without a personal-finance equivalent are excluded and their counts reported;
    - exact duplicates (same descriptor, label and amount) are de-duplicated per merchant to stop large merchants dominating;
    - **grouped split by normalised merchant**, so no merchant is in both train and test;
    - TF-IDF + logistic regression with the existing settings.
11. **Evaluation:**
    - on Oklahoma's held-out merchants: macro-F1, per-class precision and recall, and confusion matrix;
    - **independent test on DC** (a different publisher and descriptor style), with the same metrics;
    - compared against the existing keyword rule.
12. **Resources:** about 0.8 GB on disk; about 3 GB peak RAM (read in chunks, needed columns only); 5–15 minutes.
13. **Gaps:**
    - no real Indian labelled narrations exist publicly, so accuracy on Indian statements is unmeasured;
    - Rent, EMI, Investment, Transfer, Card Payment and Cash stay with the **existing Phase 4 rules** (Option A) and are labelled as rules.

## 3. Anomaly detector: Isolation Forest (methodology)

**Why ULB cannot evaluate the Oklahoma-trained model.** ULB's features are 28 PCA components of undisclosed original variables, plus `Time` and `Amount`. Finora's model uses person-relative features (ratio to own category median, robust z, share of month, ratio to own p95, source rarity, repeat count, size), which **cannot be computed** from ULB (it has no cardholder ID, no category, no merchant). Scoring ULB with the Oklahoma model would mean inventing a feature mapping, so **cross-dataset evaluation is not valid** and will not be reported.

**No public real-labelled data shares Finora's features.** I searched specifically: the real fraud sets are either PCA-anonymised (ULB) or under competition-only terms (IEEE-CIS, Vesta), and the datasets that have customer, category and amount fields with labels are synthetic (Sparkov, CreditTransAct, "Credit Card Fraud Detection Dataset 2026"), which are rejected.

**Proposed sound methodology** (one architecture, three clearly separated evidence types):
- **A. Deployed model, trained on real data.**
  - Isolation Forest on Oklahoma cardholder histories: the cardholder is a salted hash of agency + last name + initial, with **names dropped at ingestion**.
  - Same features as today; training FY2021–FY2023; **chronological** test on FY2024.
  - Reported without labels: score distribution, flag rate at the chosen contamination, and its stability across months (a genuine measure of how the model behaves on unseen data).
- **B. Deployed-model labels from blinded human review** (real labels, not planted).
  - A stratified sample of FY2024 test transactions: about 150 that the model flags, about 150 at random, and the transactions the existing **rule baseline** flags.
  - Shown **without** scores, in a simple review page, with the cardholder's own recent history for context.
  - A reviewer (you, or someone you choose; ideally two for agreement) marks each "unusual for this cardholder: yes / no / can't tell".
  - From those labels: **precision@flag, an estimated recall and false-positive rate (by sampling-weight correction), F1**, for Isolation Forest **and** the rule baseline on the same items, plus inter-rater agreement if two reviewers take part.
  - The labels are stored with the reviewer, date and instructions. **Limit:** the labels mean "unusual", not fraud.
- **C. Architecture benchmark on real fraud labels (ULB).**
  - A **separate** Isolation Forest instance on ULB's own features, trained on legitimate transactions from the first day and tested on the second day (chronological).
  - Precision, recall, F1 and false-positive rate at fixed flag rates, plus PR-AUC, against an amount-percentile rule baseline.
  - Reported as "the Isolation Forest method on real card fraud", **never** as the deployed model's accuracy.

**Datasets for this model:**
1. **Oklahoma PCard** (as in section 2, CC BY): training and chronological test.
2. **ULB credit-card fraud:**
   - OpenML 1597, https://www.openml.org/api/v1/json/data/1597;
   - file `https://openml.org/data/v1/download/1673544/creditcard.arff` (151 MB, MD5 `178bcf9bb1f31a3dfe12d0e577884add`);
   - 284,807 rows, 31 columns (`Time, V1–V28, Amount, Class`), 492 real frauds, Europe, Sept 2013;
   - OpenML licence "Public"; cite Dal Pozzolo et al. (CIDM 2015);
   - stated limit: PCA features, two days only.

**Resources:** about 0.5 GB on disk, about 2 GB RAM, under 5 minutes of training. Human review takes about 1–2 hours of reviewer time for about 300–400 items.

**Gap:** the deployed model's precision rests on human "unusual" labels from one institutional data source. No public real fraud labels with compatible features exist; obtaining them would need a data-sharing agreement with a bank or processor (route 4 below).

## 4. Cash-flow forecaster: XGBoost (not abandoned)

**Candidates found, best first:**

| Dataset | Real? | Who and when | Granularity | Size | Access | Fit |
|---|---|---|---|---|---|---|
| **PKDD'99 Financial (Berka)** | Real (CTU marks it "Real"; "a bank offering services to private persons") | Czech bank, 1993–1998 | Every transaction with balance, per account | 4,500 accounts, 5,369 clients, **1,056,320 transactions**, 682 loans, 892 cards, 77 districts, 6,471 permanent orders | Public download (CTU MariaDB guest, or the original zip about 17.5 MB). **No licence stated.** The description names **Petr Berka** (Prague University of Economics and Business, VŠE) as contact. A Kaggle mirror says CC0, but that is not the owner's statement. | **Best fit:** many real people, monthly income, spending and balance over up to 5 years, so true chronological forecasting is possible. |
| **MoneyVis "Bank Transactions Dataset"** | Real, anonymised (account name, number, sort code and personal names replaced) | One UK retail current account, Jul 2015 – mid-2022 | Transaction: date, bank-assigned type, description, debit/credit amount, running balance | **About 6,500 transactions, 1 account, 7 years** | **CC BY 4.0**, Mendeley Data DOI 10.17632/dnxtg6n4rv.1 (Laramee, University of Nottingham); paper: Firat et al., EuroVis 2023 | **Immediately usable:** genuine longitudinal personal history (about 84 months), but only **one person**. |
| **CMIE Consumer Pyramids (CPHS / Consumer Pyramids_dx)** | Real household survey | India, about 236,000 households, **monthly income** observations since 2014 (expenditure monthly, in waves) | Household-month | Very large | **Paid:** CMIE's 2026 list shows educational-institution pricing of **USD 17,500–18,500 a year**, and **Rs 30,00,000** commercial. Free account gives documentation and sample data only. Universities such as Duke and Dartmouth subscribe. | **Ideal for India:** Indian households' monthly income and spending. |
| UK open-banking research data (Salad Money via GeoDS; Spend Dynamics via the Financial Data Service; ClearScore via IFS) | Real | UK | Daily or weekly per person | Large | **Secure:** UK higher-education researchers only, inside a Trusted Research Environment | Very good, but only with a UK institutional affiliation. |
| US Financial Diaries (NYU FAI / BFA) | Real | 235 US households, one year | Fortnightly diaries | Small | No public microdata found; contact NYU Wagner's Financial Access Initiative | Possible, by request. |

**Recommended plan (no fabricated history at any stage):**
- **Stage 1, now (MoneyVis, CC BY 4.0):**
  - Build the full pipeline: transactions → monthly and weekly outflow series, lag features only, the same XGBoost architecture.
  - **Rolling-origin chronological evaluation** (train on months 1…t, predict t+1, for t = 36…83).
  - MAE and RMSE against the **3-month moving average** and last-month baselines, with actual versus predicted.
  - It is honestly reported as **one person**; generalisation across people is unproven.
- **Stage 2, after written permission (Berka):**
  - Train the cross-person model, as Finora needs, on Berka's 4,500 accounts: train to 1997-06, validate 1997-07 to 1997-12, test 1998.
  - **Use MoneyVis as a fully independent held-out test** (a different country, bank and decade).
  - Gaps: months without transactions are genuine zero-activity months; accounts with fewer than 18 months are excluded and counted.
- **Stage 3, optional (CPHS):** if your institution subscribes or you buy access, retrain or evaluate on Indian household income and expenditure.
- **Until Stage 2:** the Finora forecaster is shown as "trained on one real person's history (MoneyVis); cross-person accuracy not yet established". It is not shown as a finished model.

**Resources:** MoneyVis under 5 MB, RAM negligible, training seconds. Berka about 80 MB unpacked, under 1 GB RAM, under 2 minutes. CPHS is several GB, so a subset is needed on 8 GB RAM.

**Action needed from you:** send the Berka permission request (draft in Appendix A) to Petr Berka at VŠE. I have not contacted anyone and will not do so on your behalf.

## 5. Peer benchmarking: K-Means (not abandoned)

**Candidates:**

| Survey | Real? | Unit | Comparable variables | Size | Access |
|---|---|---|---|---|---|
| **Federal Reserve Survey of Consumer Finances 2022** | Real survey | **Household ("family")** | `INCOME, WAGEINC, TOTSPENDNH, SAVED, WSAVED, LIQ, FIN, NFIN, ASSET, DEBT, NETWORTH, DEBT2INC, PIRTOTAL, CCBAL, EQUITY, RETQLIQ, LATE, EMERGSAV, AGE, KIDS, WGT` (verified from the 362-column extract) | 4,595 families, stored as 22,975 records (5 imputations) | **Public download** (the summary extract CSV is 2 MB zipped), https://www.federalreserve.gov/econres/scf_2022.htm, codebook `codebk2022.txt`. The page states no restriction. A US Federal Reserve publication; cite the Fed. |
| **India: All India Debt & Investment Survey 2019 (NSS 77th round, Schedule 18.2)** | Real survey | Household | Assets (land, buildings, financial assets, deposits, shares), debt (cash loans by source, interest rate), household characteristics, consumption expenditure | About 1.16 lakh households (MoSPI report figure; to be confirmed after registration) | **Free registration** at https://microdata.gov.in/NADA/index.php/catalog/156 ("user must be logged in"; "free account"). Terms are in the MoSPI dissemination policy, which **must be read when you register**. |
| ECB Household Finance and Consumption Survey | Real | Household | Income, assets, liabilities, consumption | About 80,000+ households | **Application** to `hfcs.access@ecb.europa.eu` with ID, CV and a research request form; for research purposes |
| UK Wealth and Assets Survey (UK Data Service SN 7215) | Real | Household and individual | Wealth, debt, income | Large | UK Data Service licence; access level **not verified** (the catalogue page could not be read) |
| CMIE CPHS (see section 4) | Real | Household | Income, expenditure, assets | Large | Paid |

**How the data supports peer groups.**
- **Features:** K-Means runs on **ratios a Finora user can also compute**, so peers are comparable whatever the currency:
  - savings indicator (`SAVED`) and spending-to-income (`TOTSPENDNH × 12 / INCOME`);
  - liquid assets / monthly income (`LIQ / (INCOME/12)`, emergency months);
  - `DEBT2INC`, debt payments / income (`PIRTOTAL`), card balance / income;
  - financial assets / total assets, equity share, net worth / income, and age band.
- **Weights and imputations:** survey weights (`WGT`) are used as K-Means sample weights. The 5 imputations are averaged per family, never treated as separate people.
- **k and stability:** k is chosen by silhouette; stability is checked by bootstrap adjusted Rand index.
- **Household versus individual:** SCF and AIDIS are **household-level**. A Finora profile is one person, so the comparison is labelled "households like yours". Finora users enter their own household or individual figures, and the UI says which applies.

**Recommended plan:**
- **Stage 1, now:** SCF 2022 (public) gives a working real-data K-Means immediately, labelled "US households, 2022".
- **Stage 2:** **AIDIS 2019** for Indian peer groups after you register on microdata.gov.in and accept its terms (I cannot register for you). Indian users are then compared with Indian households; SCF stays as an option.
- **Optional:** ECB HFCS (an application) or CPHS (paid).

**Resources:** SCF about 20 MB, under 0.5 GB RAM, seconds. AIDIS about 0.5–1 GB of text files, under 2 GB RAM, about a minute.

## 6. AI CFO: Qwen 2.5 via Ollama (no training)

**Provenance to record:**
- the Qwen 2.5 family from the Alibaba Qwen team; the Ollama tag `qwen2.5:3b`, digest `357c53fb659c`, 1.9 GB, installed 13 days before this audit;
- quantisation and the licence published for that size will be read from `ollama show` and the model card in Phase 7.

**Discrepancy, documented and not changed:** `backend/.env` (`OLLAMA_MODEL=qwen3.5:4b`) and the code default (`app/config.py`) select **qwen3.5:4b**, which is not Qwen 2.5 and is not installed. Switching to Qwen 2.5 and verifying number-checking belong to Phase 7.

## 7. Legacy artifacts (approved: move, do not delete)

To be done in the training step, not before, so the app never runs without models:
- the current five artifacts and `metrics.json` move to `artifacts/legacy-synthetic-2026-11-13/` with a README;
- the registry loads only artifacts whose provenance record says `data_status: real` and `approved: true`;
- a model without one shows as **"not available: awaiting real-data training"** in the app and Model Lab, never silently falling back;
- rollback is a documented one-line config switch (`MODEL_SET=legacy-synthetic`), clearly labelled synthetic wherever shown.

## Access routes in one place
1. **Public download, no barrier:** UCI (CC BY 4.0), Oklahoma FY2021–24 (CC BY), DC (CC BY 4.0), MoneyVis (CC BY 4.0), SCF 2022 (Fed public), ULB via OpenML ("Public").
2. **Free registration by you:** AIDIS 2019 on microdata.gov.in.
3. **Written permission by you:** Berka (Petr Berka, VŠE; draft below).
4. **Application or institution:** ECB HFCS (research request); UK open-banking data (UK higher-education researchers, Trusted Research Environment); US Financial Diaries (contact NYU Wagner FAI); a bank or processor data-sharing agreement for real labelled anomalies.
5. **Paid:** CMIE Consumer Pyramids (about USD 17.5k a year academic; Rs 30 lakh commercial), unless your institution already subscribes.

## Approvals requested
1. **Downloads:** credit risk and categoriser downloads (already approved), plus **SCF 2022**, **MoneyVis** and **ULB** (each under 160 MB).
2. **Anomaly methodology:** A + B + C above, including who will do the blinded review (you, and optionally a second reviewer).
3. **Forecaster:** Stage 1 on MoneyVis now; Stage 2 Berka once **you** have sent the permission request and the owner replies.
4. **Peers:** Stage 1 on SCF now; Stage 2 AIDIS once **you** register on microdata.gov.in.
5. **Rollout:** the registry and legacy-artifact changes in section 7.

---

## Appendix A: draft permission request (for you to send; not sent)

> Subject: Permission to use the PKDD'99 Discovery Challenge financial dataset
>
> Dear Dr Berka,
>
> I am building Finora, an educational personal-finance analysis application, as an academic project. I would like to use the PKDD'99 Discovery Challenge financial dataset (accounts, clients, transactions, loans, cards) to train and evaluate a cash-flow forecasting model (XGBoost) and to describe its provenance accurately.
>
> I could not find a licence or terms of use on the challenge page or the CTU Relational repository. Could you confirm whether the dataset may be used for this purpose, under what conditions, and how you would like it to be cited? I will not redistribute the data, and I will state that it comes from a Czech bank in the 1990s and is not representative of Indian households.
>
> Thank you,
> [your name, institution, contact]

## Sources read for this report
- UCI dataset 350 and its official zip (verified locally): https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
- Oklahoma PCard (CKAN API and file header): https://data.ok.gov/dataset/purchase-card-pcard-fiscal-year-2024
- DC PCard: https://catalog.data.gov/dataset/purchase-card-transactions (CC BY 4.0) and its CSV header
- OpenML 1597: https://www.openml.org/api/v1/json/data/1597
- PKDD'99 data description (archived): http://lisp.vse.cz/pkdd99/Challenge/berka.htm via web.archive.org; CTU: https://relational.fel.cvut.cz/dataset/Financial
- MoneyVis: https://data.mendeley.com/datasets/dnxtg6n4rv/1 and https://people.cs.nott.ac.uk/blaramee/research/financeVis/firat23moneyVis.pdf
- SCF 2022: https://www.federalreserve.gov/econres/scf_2022.htm (summary extract header read)
- AIDIS 2019: https://microdata.gov.in/NADA/index.php/catalog/156
- ECB HFCS: https://www.ecb.europa.eu/stats/ecb_surveys/hfcs/html/index.en.html
- CMIE: https://consumerpyramidsdx.cmie.com/ and https://dupri.duke.edu/sites/default/files/2021-06/Accessing%20CMIE%20Consumer%20Pyramids%20Data.pdf
- UK: https://data.geods.ac.uk/dataset/salad-money-open-banking-transaction-data, https://www.sdruk.ukri.org/find-data/featured-datasets-and-tools/spend-dynamics/, https://ifs.org.uk/publications/unemployment-benefits-and-household-spending-new-evidence-uk-bank-account-data
- US Financial Diaries: https://www.usfinancialdiaries.org/about

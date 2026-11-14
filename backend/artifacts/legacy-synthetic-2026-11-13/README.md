# Legacy synthetic-trained artifacts (kept for rollback, never loaded by default)

These five models and their `metrics.json` were trained before Phase 6 on Finora's **synthetic** population
(and, for credit risk, the UCI Taiwan data). They are moved here, unchanged, on 2026-11-15. They are **not deleted**.

| file | SHA-256 |
|---|---|
| anomaly.joblib | f50a3b3dc86658222ab86a9c502b638d6d3e4e247f72b509269f809070cdf375 |
| categoriser.joblib | d7e83205fae8ab61c7f188914f585dc484e65b7dba8146676423f82ece8f3b54 |
| credit_risk.joblib | e8d7e42804faa493cf9c2c9ea77e8fd5b3a002fe5f764a27f606c2cb5f15f098 |
| forecast.joblib | 3138fb1494c06e6488f5a6300a0cdc4043d664f6813fb2f3e6eae5874241a8ed |
| peers.joblib | 7c5a571397837ffeddf6b99ecfc021069703c4dd98e36ac5ee363d41532cd944 |
| metrics.json | e9ad59c4e2cfe2af55b4e882a7df6b741b76df99a0b02d702f41e57c883d4f21 |

- The app loads only the real-data versions listed in `artifacts/active.json`.
- A model without one shows **"awaiting real-data training"**. There is no silent fallback to these files.
- Development rollback only: start the server with `MODEL_SET=legacy-synthetic`. Model Lab then labels every model as
  synthetic-trained.
- The code that trained them is in git history (commit 26b5a83, `app/ml/train.py`, `app/ml/population.py`).

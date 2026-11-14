"""Merchant-category classifier: TF-IDF + logistic regression (the existing architecture and settings) on REAL card
transaction descriptors (Oklahoma FY2021-24), evaluated on held-out merchants and on two independent real sources:
District of Columbia purchase cards (another government publisher) and MoneyVis (one UK personal account, categories assigned
by people). This is merchant-category classification; it is NOT validated on Indian bank-statement narrations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit

from .. import categoriser as CG
from ..data import moneyvis as MV
from ..data import pcard as PC
from ..provenance import Run, sha256, source_record

SEED = 7
CAP_PER_MERCHANT = 40       # at most this many distinct descriptors per merchant group, so big chains cannot dominate
# MoneyVis categories assigned by people -> Finora merchant categories (only clear one-to-one meanings are used)
MONEYVIS_MAP = {"Groceries": "Groceries", "Dine Out": "Dining", "Travel": "Travel", "Hotels": "Travel",
                "Entertainment": "Entertainment", "Clothes": "Shopping", "Other Shopping": "Shopping", "Amazon": "Shopping",
                "Insurance": "Insurance", "Health": "Health"}


def cap_per_merchant(d: pd.DataFrame) -> pd.DataFrame:
    """At most CAP_PER_MERCHANT distinct descriptors per merchant group (random but seeded), so big chains cannot dominate."""
    d = d.sample(frac=1.0, random_state=SEED)
    return d[d.groupby("group").cumcount() < CAP_PER_MERCHANT].reset_index(drop=True)


REVIEW_BELOW = 0.5          # the existing review threshold in categoriser.predict (unchanged): below it, the person is asked
RARE = 100                  # categories with fewer training descriptors than this are reported as rare


def _eval(model, texts, y, labels) -> dict:
    proba = model.predict_proba(list(texts))
    pred = model.classes_[proba.argmax(axis=1)]
    conf = proba.max(axis=1)
    sure = conf >= REVIEW_BELOW
    yy = np.asarray(y)
    kw = [CG.keyword_rule(t) for t in texts]
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=labels, zero_division=0)
    present = [l for l in labels if (np.asarray(y) == l).any()]
    return {"rows": int(len(y)), "macro_f1": round(float(f1_score(y, pred, labels=present, average="macro", zero_division=0)), 4),
            "accuracy": round(float((np.asarray(pred) == np.asarray(y)).mean()), 4),
            "keyword_rule_macro_f1": round(float(f1_score(y, kw, labels=present, average="macro", zero_division=0)), 4),
            "keyword_rule_accuracy": round(float((np.asarray(kw) == np.asarray(y)).mean()), 4),
            "per_class": [{"category": l, "precision": round(float(a), 3), "recall": round(float(b), 3), "f1": round(float(c), 3),
                           "support": int(d)} for l, a, b, c, d in zip(labels, p, r, f, s)],
            "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y, pred, labels=labels).tolist()},
            "class_distribution": {l: int((yy == l).sum()) for l in labels},
            "confidence": {"review_threshold": REVIEW_BELOW, "share_confident": round(float(sure.mean()), 4),
                           "accuracy_when_confident": round(float((pred[sure] == yy[sure]).mean()), 4) if sure.any() else None,
                           "accuracy_when_sent_for_review": round(float((pred[~sure] == yy[~sure]).mean()), 4) if (~sure).any() else None}}


def train(approved: bool) -> tuple[str, dict]:
    run = Run("categoriser", "python -m app.ml.train categoriser")
    ok, ok_rep = PC.load_oklahoma()
    data, mapping = PC.labelled(ok)
    data = cap_per_merchant(data)
    PC.OUT.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(PC.OUT / "mcc_mapping.csv", index=False)
    data.to_csv(PC.OUT / "categoriser_oklahoma.csv.gz", index=False)
    labels = sorted(data["category"].unique())
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    tr_idx, te_idx = next(gss.split(data, groups=data["group"]))
    tr, te = data.iloc[tr_idx], data.iloc[te_idx]
    assert not set(tr["group"]) & set(te["group"]), "merchant leakage between train and test"
    model = CG._pipeline(SEED).fit(tr["text"], tr["category"])
    held = _eval(model, te["text"], te["category"], labels)
    # independent source 1: District of Columbia (different publisher, different descriptor style)
    dc, dc_rep = PC.load_dc()
    dcl, dc_map = PC.labelled(dc)
    dc_map.to_csv(PC.OUT / "mcc_mapping_dc.csv", index=False)
    dc_eval = _eval(model, dcl["text"], dcl["category"], labels)
    dc_eval["merchants_also_in_oklahoma_training"] = int(dcl["group"].isin(set(tr["group"])).sum())
    unseen = dcl[~dcl["group"].isin(set(tr["group"]))]
    dc_eval["unseen_merchants_only"] = {k: v for k, v in _eval(model, unseen["text"], unseen["category"], labels).items()
                                        if k in ("rows", "macro_f1", "accuracy", "keyword_rule_macro_f1", "keyword_rule_accuracy")}
    # independent source 2: MoneyVis (UK personal account; categories assigned by people), merchant categories only
    mv, _ = MV.transactions()
    mv = mv[(mv["debit"] > 0) & mv["category"].isin(MONEYVIS_MAP)]
    mv = mv.assign(text=mv["description"].astype(str).str.upper().str.replace(r"\s+", " ", regex=True),
                   label=mv["category"].map(MONEYVIS_MAP)).drop_duplicates(subset=["text", "label"])
    mv_eval = _eval(model, mv["text"], mv["label"], labels)
    tr_text = set(tr["text"])
    leakage = {"merchant_groups_in_both": int(len(set(tr["group"]) & set(te["group"]))),
               "test_descriptors_identical_to_a_training_descriptor": int(te["text"].isin(tr_text).sum()),
               "dc_rows_whose_descriptor_is_in_oklahoma_training": int(dcl["text"].isin(tr_text).sum()),
               "dc_rows_whose_merchant_group_is_in_oklahoma_training": dc_eval["merchants_also_in_oklahoma_training"],
               "method": "GroupShuffleSplit by merchant group; descriptors de-duplicated per (text, label) before splitting"}
    counts = data["category"].value_counts()
    rare = {c: {"training_descriptors": int(counts[c]), "held_out_f1": next(p["f1"] for p in held["per_class"] if p["category"] == c),
                "held_out_support": next(p["support"] for p in held["per_class"] if p["category"] == c)}
            for c in labels if counts[c] < RARE}
    final = CG._pipeline(SEED).fit(data["text"], data["category"])     # deployment model: all Oklahoma groups
    passed = bool(held["macro_f1"] >= 0.50 and held["macro_f1"] > held["keyword_rule_macro_f1"]
                  and dc_eval["macro_f1"] > dc_eval["keyword_rule_macro_f1"])                   # = acceptance.CRITERIA["categoriser"]
    metrics = {
        "task": "Merchant-category classification of card transaction descriptors (not Indian bank-statement narrations)",
        "categories_learned": labels, "bank_side_categories": "Rent, EMI, Investment, Transfer, Card Payment, Cash: rules, not ML",
        "training": {"rows": int(len(data)), "merchant_groups": int(data["group"].nunique()), "cap_per_merchant": CAP_PER_MERCHANT,
                     "class_counts": data["category"].value_counts().to_dict()},
        "split": "GroupShuffleSplit 80/20 by merchant group (no merchant in both train and test), random_state=7",
        "held_out_merchants_oklahoma": held, "independent_test_dc": dc_eval, "independent_test_moneyvis_uk_personal": mv_eval,
        "beats_keyword_rule_on_held_out": bool(passed),
        "leakage_checks": leakage, "rare_categories": rare,
        "unmapped": {"mcc_descriptions_total": int(len(mapping)), "mcc_descriptions_excluded": int(mapping["finora_category"].isna().sum()),
                     "transaction_rows_excluded": int(mapping.loc[mapping["finora_category"].isna(), "rows"].sum()),
                     "transaction_rows_total": int(mapping["rows"].sum()),
                     "dc_transaction_rows_excluded": int(dc_map.loc[dc_map["finora_category"].isna(), "rows"].sum()),
                     "rule": "MCC descriptions with no personal-finance meaning (app/ml/data/pcard.EXCLUDED) or no match are excluded, "
                             "never forced into a category"},
        "keyword_baseline_note": "The keyword rules were written for Indian merchant names (Swiggy, BigBasket ...), so on US descriptors "
                                 "they mostly fall back to Shopping; beating them is a low bar, which is why macro-F1 >= 0.50 is also required.",
    }
    ok_src, dc_src, mv_src = source_record("oklahoma_pcard"), source_record("dc_pcard"), source_record("moneyvis")
    excluded = mapping[mapping["finora_category"].isna()]
    prov = {
        "data_status": "real", "evaluation_passed": bool(passed), "approved_by_owner": bool(approved),
        "deployment_label": "Merchant categories learned from real US government purchase-card transactions; not validated on "
                            "Indian bank statements. Rent, EMI, Investment, Transfer, Card Payment and Cash are rules.",
        "datasets": [
            {"key": "oklahoma_pcard", "role": "training + held-out merchant test", "name": ok_src.get("name"), "publisher": ok_src.get("publisher"),
             "source_url": ok_src.get("page"), "licence": ok_src.get("licence"), "geography": "Oklahoma, USA",
             "collection_period": f"{ok_rep['date_from']} to {ok_rep['date_to']} (FY2021-FY2024)", "records": ok_rep["rows"],
             "files": [{"file": f["file"], "sha256": f["sha256"], "url": f["url"]} for f in ok_src.get("files", [])],
             "observations": "real", "synthetic_observations": "none", "downloaded": ok_src.get("downloaded_at"),
             "cleaning": ok_rep, "labels": "card network MCC description, mapped by app/ml/data/pcard.MCC_RULES",
             "mcc_descriptions_total": int(len(mapping)), "mcc_descriptions_excluded": int(len(excluded)),
             "rows_excluded_by_mapping": int(excluded["rows"].sum()), "mapping_file_sha256": sha256(PC.OUT / "mcc_mapping.csv"),
             "duplicates": "one row per distinct descriptor + label; at most 40 descriptors per merchant group",
             "known_biases": "Institutional (government/university) spending, US merchants, US descriptor formats."},
            {"key": "dc_pcard", "role": "independent test", "name": dc_src.get("name"), "publisher": dc_src.get("publisher"),
             "source_url": dc_src.get("page"), "licence": dc_src.get("licence"), "geography": "Washington DC, USA",
             "collection_period": f"{dc_rep['date_from']} to {dc_rep['date_to']}", "records": dc_rep["rows"],
             "files": [{"file": f["file"], "sha256": f["sha256"], "url": f["url"]} for f in dc_src.get("files", [])],
             "observations": "real", "synthetic_observations": "none", "downloaded": dc_src.get("downloaded_at"), "cleaning": dc_rep},
            {"key": "moneyvis", "role": "independent test (UK personal account, people-assigned categories)",
             "name": mv_src.get("name"), "source_url": mv_src.get("page"), "licence": mv_src.get("licence"),
             "files": [{"file": f["file"], "sha256": f["sha256"]} for f in mv_src.get("files", [])], "observations": "real",
             "category_mapping": MONEYVIS_MAP}],
        "methodology": "TF-IDF (character 2-5-grams + words, digits collapsed) + logistic regression C=8 (unchanged); deployed model "
                       "refit on all Oklahoma groups after evaluation.",
        "limitations": "US institutional card descriptors. Accuracy on Indian UPI/NEFT narrations is NOT measured (no real labelled "
                       "Indian data is publicly available). Personal categories such as Subscriptions may be under-represented.",
        "processed_files": {"categoriser_oklahoma.csv.gz": sha256(PC.OUT / "categoriser_oklahoma.csv.gz")},
        "reproducible": "python -m app.ml.train categoriser (seed 7) with the raw files above",
    }
    out = run.save({"model": final, "labels": labels}, metrics, prov)
    return run.version, {"out": str(out), "held": {k: held[k] for k in ("rows", "macro_f1", "accuracy", "keyword_rule_macro_f1")},
                         "dc": {k: dc_eval[k] for k in ("rows", "macro_f1", "accuracy", "keyword_rule_macro_f1", "unseen_merchants_only")},
                         "moneyvis": {k: mv_eval[k] for k in ("rows", "macro_f1", "accuracy", "keyword_rule_macro_f1")},
                         "training": metrics["training"], "excluded_rows": int(excluded["rows"].sum())}

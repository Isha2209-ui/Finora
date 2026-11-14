"""Transaction Categoriser - turns raw bank-statement narrations into spending categories.

    "UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment"  ->  Dining

Model: character n-gram TF-IDF (2-5 chars, robust to codes, truncation and typos)
       + word TF-IDF, fed to a linear classifier (logistic regression).
Training data: labelled narrations generated from realistic templates of 15 Indian
       bank / card / wallet statement formats (app/data/narrations.py).
Honest evaluation: the model is tested on statement FORMATS and MERCHANT spellings
       it never saw in training, and compared with a keyword-rule baseline.
"""
from __future__ import annotations

import random
import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from ..data import narrations as N

HELD_OUT_FORMATS = ["kotak_upi", "razorpay", "phonepe"]  # never seen in training
SPECIAL = ["EMI", "Investment", "Rent", "Cash", "Card Payment", "Transfer", "Insurance"]
MERCHANT_CATS = [c for c in N.MERCHANTS if c not in {"Rent", "EMI", "Investment", "Card Payment", "Transfer", "Cash"}]
LENDERS = ["HDFC Bank", "SBI Home Loans", "Bajaj Finance", "Axis Bank", "ICICI Bank", "Tata Capital", "LIC Housing"]
SCHEMES = ["Parag Parikh Flexi Cap", "UTI Nifty 50 Index", "Axis ELSS", "Mirae Asset Large Cap", "Quant Small Cap",
           "HDFC Short Term Debt", "SBI Bluechip"]

_DIGITS = re.compile(r"\d{3,}")


def normalise(text: str) -> str:
    return _DIGITS.sub(" # ", str(text).upper())


def _noisy(text: str, rng: random.Random) -> str:
    """Mimic real statements: truncation, case changes, dropped separators."""
    r = rng.random()
    if r < 0.12:
        return text[: max(14, int(len(text) * rng.uniform(0.55, 0.9)))]
    if r < 0.20:
        return text.lower()
    if r < 0.28:
        return text.replace("-", " ").replace("/", " ")
    return text


def build_dataset(n_per_cat: int = 900, seed: int = 11) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for cat in MERCHANT_CATS:
        for _ in range(n_per_cat):
            desc, merch, fmt = N.merchant_narration(cat, rng)
            rows.append((_noisy(desc, rng), cat, fmt, merch))
    for cat in SPECIAL:
        for _ in range(n_per_cat // 2):
            desc = N.special_narration(cat, rng, lender=rng.choice(LENDERS), bank=rng.choice(list(N.BANK_UPI_FORMAT)),
                                       scheme=rng.choice(SCHEMES), card=rng.choice(LENDERS), city=rng.choice(N.CITIES))
            rows.append((_noisy(desc, rng), cat, "special", None))
    return pd.DataFrame(rows, columns=["text", "category", "format", "merchant"])


def _pipeline(seed: int) -> Pipeline:
    feats = FeatureUnion([
        ("char", TfidfVectorizer(preprocessor=normalise, analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ("word", TfidfVectorizer(preprocessor=normalise, analyzer="word", token_pattern=r"[A-Z]{2,}", ngram_range=(1, 2), min_df=2)),
    ])
    return Pipeline([("tfidf", feats), ("clf", LogisticRegression(C=8.0, max_iter=3000, random_state=seed))])


# ---- keyword-rule baseline (what a developer would write without ML)
KEYWORDS = {
    "Dining": ["SWIGGY", "ZOMATO", "RESTAURANT", "CAFE", "PIZZA"], "Groceries": ["BIGBASKET", "GROCER", "DMART", "KIRANA"],
    "Shopping": ["AMAZON", "FLIPKART", "MYNTRA"], "Travel": ["UBER", "OLA", "IRCTC", "FLIGHT"], "Fuel": ["PETROL", "FUEL", "IOCL"],
    "Entertainment": ["BOOKMYSHOW", "PVR", "MOVIE"], "Subscriptions": ["NETFLIX", "SPOTIFY", "PRIME"],
    "Utilities": ["ELECTRICITY", "AIRTEL", "JIO", "BILL"], "Health": ["PHARMACY", "HOSPITAL", "MEDICAL"],
    "Education": ["COURSE", "SCHOOL", "FEES"], "Insurance": ["INSURANCE", "LIC", "PREMIUM"], "Rent": ["RENT"],
    "EMI": ["EMI", "LOAN"], "Investment": ["SIP", "MUTUAL", "BSE"], "Cash": ["ATM", "CASH"],
    "Card Payment": ["CREDIT CARD", "CC PAYMENT"], "Transfer": ["SELF", "OWN ACCOUNT"],
}


def keyword_rule(text: str) -> str:
    t = str(text).upper()
    for cat, kws in KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return "Shopping"


def train(seed: int = 7) -> tuple[dict, dict]:
    df = build_dataset(seed=seed + 4)
    held = df["format"].isin(HELD_OUT_FORMATS)
    rng = np.random.default_rng(seed)
    in_dist_test = (~held) & (rng.random(len(df)) < 0.15)
    tr = df[~held & ~in_dist_test]
    model = _pipeline(seed).fit(tr["text"], tr["category"])

    def score(part: pd.DataFrame) -> dict:
        pred = model.predict(part["text"])
        rule = part["text"].map(keyword_rule)
        return {"rows": int(len(part)), "accuracy": round(float(accuracy_score(part["category"], pred)), 4),
                "macro_f1": round(float(f1_score(part["category"], pred, average="macro")), 4),
                "keyword_rule_accuracy": round(float(accuracy_score(part["category"], rule)), 4),
                "keyword_rule_macro_f1": round(float(f1_score(part["category"], rule, average="macro")), 4)}

    unseen = df[held]
    # hardest test: merchants the model has never seen at all (one per category held out completely)
    hold_merch = {c: sorted(set(m for m, _ in N.MERCHANTS[c]))[-1] for c in MERCHANT_CATS if len(set(m for m, _ in N.MERCHANTS[c])) > 2}
    is_new = df.apply(lambda r: hold_merch.get(r["category"]) == r["merchant"], axis=1)
    m2 = _pipeline(seed).fit(df[~is_new]["text"], df[~is_new]["category"])
    new_part = df[is_new]
    new_pred = m2.predict(new_part["text"])
    new_merchants = {"rows": int(len(new_part)), "merchants_held_out": sorted(hold_merch.values()),
                     "accuracy": round(float(accuracy_score(new_part["category"], new_pred)), 4),
                     "keyword_rule_accuracy": round(float(accuracy_score(new_part["category"], new_part["text"].map(keyword_rule))), 4)}
    labels = sorted(df["category"].unique())
    cm = confusion_matrix(unseen["category"], model.predict(unseen["text"]), labels=labels)
    seen, unseen_m = score(df[in_dist_test]), score(unseen)
    metrics = {
        "model": "TF-IDF (char 2-5 grams + words) + Logistic Regression", "categories": labels,
        "training_rows": int(len(tr)), "statement_formats_total": len(N.FORMATS), "held_out_formats": HELD_OUT_FORMATS,
        "seen_formats_test": seen, "unseen_formats_test": unseen_m, "never_seen_merchants_test": new_merchants,
        "beats_keyword_rule": unseen_m["macro_f1"] > unseen_m["keyword_rule_macro_f1"],
        "confusion_matrix_unseen_formats": {"labels": labels, "matrix": cm.tolist()},
        "limitations": "Training narrations are generated from realistic templates, not scraped bank statements. "
                       "Unknown local merchants fall back to the nearest known pattern; low-confidence results are shown for review.",
    }
    # final model: refit on everything
    final = _pipeline(seed).fit(df["text"], df["category"])
    return {"model": final}, metrics


def predict(art: dict, texts: list[str]) -> list[dict]:
    if not texts:
        return []
    proba = art["model"].predict_proba(texts)
    classes = art["model"].classes_
    out = []
    for row in proba:
        k = int(np.argmax(row))
        out.append({"category": str(classes[k]), "confidence": round(float(row[k]), 3), "needs_review": bool(row[k] < 0.5)})
    return out


# ---------------------------------------------------------------- bank-side categories: RULES, not ML (Phase 6 decision, Option A)
# Rent, EMI, Investment, Transfer, Card Payment and Cash are bank-side transaction types, not merchant categories, and no real
# labelled data exists for them. They are recognised by these narration rules, applied BEFORE the model and labelled "rule".
BANK_SIDE_RULES = [
    ("Card Payment", re.compile(r"credit\s*card|\bcc\s*(?:payment|pymt|bill)|card\s*(?:bill|payment)|\bcred\b|cardpay", re.I)),
    ("Transfer", re.compile(r"\bself\b|own\s*(?:a/?c|acc|account)|\bsweep\b|trf\s+to\s+self|\bto\s+own\b", re.I)),
    ("Investment", re.compile(r"\bsip\b|mutual\s*fund|\bmf\b|bse\s*(?:star|ltd)|\bcams\b|kfin|zerodha|groww|\bnps\b|\bppf\b|"
                              r"\belss\b|\bnifty\b|flexi\s*cap|large\s*cap|small\s*cap|index\s*fund", re.I)),
    ("EMI", re.compile(r"\bemi\b|\bloan\b|home\s*fin|\bnach\b.*(?:fin|bank|capital)|\becs\b", re.I)),
    ("Rent", re.compile(r"\brent\b|landlord", re.I)),
    ("Cash", re.compile(r"\batm\b|cash\s*(?:wdl|withdrawal)|\bnwd\b|\batw\b|cashpoint", re.I)),
]


def bank_side_rule(text: str) -> str | None:
    for cat, rx in BANK_SIDE_RULES:
        if rx.search(str(text)):
            return cat
    return None


# Phase 6 (2026-11-15): the approved categoriser passes its acceptance criteria on held-out US merchants and on DC, but it is not
# validated on Indian bank narrations, and on Finora's Indian-format test narrations its confident predictions agreed with the
# intended category only ~44% of the time. Until real labelled Indian data exists, every model category is a SUGGESTION that
# the person confirms (needs_review=True); rules and the person's own choices are not affected.
SUGGESTION_ONLY = True


def safe_predict(texts: list[str]) -> list[dict]:
    """Bank-side rules first, then the APPROVED real-data model if one is available. Each result says who decided:
    source = 'rule' | 'model' | 'none' (no approved model: the category is left empty for the person to set)."""
    from . import registry
    out: list[dict | None] = []
    todo = []
    for i, t in enumerate(texts):
        c = bank_side_rule(t)
        if c:
            out.append({"category": c, "confidence": 1.0, "needs_review": False, "source": "rule"})
        else:
            out.append(None)
            todo.append(i)
    if todo:
        try:
            art = registry.get("categoriser")
            preds = predict(art, [texts[i] for i in todo])
            for i, p in zip(todo, preds):
                out[i] = {**p, "source": "model", "needs_review": True if SUGGESTION_ONLY else p["needs_review"]}
        except registry.ModelUnavailable:
            for i in todo:
                out[i] = {"category": None, "confidence": None, "needs_review": True, "source": "none"}
    return out


_NAMES: dict[int, object] = {}


def explain(art: dict, text: str, k: int = 4) -> list[str]:
    """The text fragments that pushed the linear model towards its predicted class (TF-IDF weight x class coefficient).
    Real model internals, not a made-up rationale. Fragments are character n-grams or words from the descriptor."""
    pipe = art["model"]
    feats, clf = pipe.named_steps["tfidf"], pipe.named_steps["clf"]
    key = id(pipe)
    if key not in _NAMES:
        _NAMES[key] = feats.get_feature_names_out()
    names = _NAMES[key]
    x = feats.transform([text])
    k_cls = int(np.argmax(clf.predict_proba(x)[0]))
    coef = clf.coef_[k_cls] if clf.coef_.shape[0] > 1 else clf.coef_[0]
    row = x.tocoo()
    contrib = sorted(((v * coef[j], names[j]) for j, v in zip(row.col, row.data)), reverse=True)
    out, seen = [], set()
    for c, name in contrib:
        if c <= 0:
            break
        frag = name.split("__", 1)[-1].strip()
        if len(frag) >= 3 and frag.lower() not in seen and not any(frag.lower() in s_ for s_ in seen):
            seen.add(frag.lower())
            out.append(frag)
        if len(out) >= k:
            break
    return out

"""Real purchase-card data (Oklahoma FY2021-24, CC BY; District of Columbia, CC BY 4.0): load, clean, label.

Labels: the card network's merchant category (MCC description) mapped to Finora's MERCHANT categories by the explicit rules
below. The full mapping actually applied is written to datasets/processed/pcard/mcc_mapping.csv for review. MCC groups with
no personal-finance meaning (industrial supplies, government services, postage, professional services ...) are EXCLUDED and
counted - never forced into a category. Bank-side categories (Rent, EMI, Investment, Transfer, Card Payment, Cash) are not
merchant categories and are not learned here (they are rules: categoriser.BANK_SIDE_RULES).

Privacy: cardholder names are used only to build a salted one-way hash per cardholder (agency + last name + initial) for the
anomaly model, and are never written to processed files.
"""
from __future__ import annotations

import glob
import hashlib
import re

import pandas as pd

from ...config import DATASETS_DIR, PAN_PEPPER

RAW = DATASETS_DIR / "raw"
OUT = DATASETS_DIR / "processed" / "pcard"

# MCC descriptions are matched after normalisation (lower case, punctuation -> single spaces), because the publisher spells the
# same MCC several ways ("CABLE, SATELLITE" / "CABLE  SATELLITE"). EXCLUDED is checked first: institutional, trade, B2B and
# fee MCCs have no personal-finance meaning and are never forced into a category. Then MCC_RULES, first match wins.
EXCLUDED = ["equipment", "industrial", "contractor", "government services", "business services", "professional services",
            "commercial", "freight", "courier", "postage", "advertising", "chemical", "construction", "metal service", "welding",
            "warehousing", "durable goods", "typesetting", "stenographic", "janitorial", "employment agenc", "engineering",
            "management consulting", "detective", "agricultural", "tax payments", "fines", "court costs", "funding transactions",
            "credit reporting", "other fees", "direct marketers", "catalog", "data processing", "drug proprietaries",
            "quick copy", "publishing", "photocopy", "membership organizations", "civic social", "charitable", "political",
            "religious organizations", "legal services", "accounting", "real estate", "exterminating", "landscape", "cleaning",
            "repair", "towing", "car washes", "dealers", "marinas", "veterinary", "information retrieval", "photographic studios",
            "photofinishing", "commercial photography", "personal services", "beauty", "barber", "massage", "spas", "dry cleaners",
            "laundr", "tailors", "child care", "funeral", "counseling", "masonry", "roofing", "carpentry", "plumbing", "wrecking",
            "salvage", "paints varnishes", "equip rentals", "autograph", "recreational and utility trailer"]
MCC_RULES = [
    ("Fuel", ["service station", "fuel dealer", "automated fuel", "petroleum", "gasoline"]),
    ("Dining", ["restaurant", "fast food", "eating place", "caterer", "drinking place", "bakeries", "bakery"]),
    ("Groceries", ["grocery", "supermarket", "convenience store", "dairy product", "candy", "meat provision", "food store",
                   "wholesale clubs"]),
    ("Travel", ["airline", "air carrier", "airport", "airways", "air lines", "air canada", "lufthansa", "finnair", "hawaiian air",
                "delta", "lodging", "hotel", "motel", "resort", " inn", "inns", "suites", "hilton", "marriot", "hyatt", "sheraton",
                "westin", "wyndham", "doubletree", "radisson", "aloft", "econolodge", "extended stay", "gaylord", "campground",
                "taxicab", "limousine", "car rental", "rent a car", "hertz", "automobile rental", "truck and utility trailer rental",
                "railroad", "passenger railway", "bus line", "travel agenc", "toll", "parking", "transportation services",
                "ferries", "cruise", "commuter"]),
    ("Health", ["drug store", "pharmac", "doctors", "dentists", "orthodontists", "hospitals", "medical services", "optician",
                "optometr", "health practitioner", "nursing", "chiropract", "osteopath", "podiatr", "hearing aid", "orthopedic goods"]),
    ("Insurance", ["insurance"]),
    ("Education", ["schools and educational", "colleges universities", "business and secretarial schools", "vocational",
                   "trade schools", "correspondence schools", "dance halls studios and schools"]),
    ("Utilities", ["utilities", "telecommunication", "telephone service", "cable satellite", "internet", "water sanitary"]),
    ("Subscriptions", ["digital goods", "streaming", "subscription", "pay television"]),
    ("Entertainment", ["motion picture", "theater", "theatre", "theatrical", "amusement", "recreation", "bowling",
                       "tourist attraction", "video game", "video rental", "entertain", "sports club", "golf", "museum"]),
    ("Shopping", ["department store", "discount store", "variety store", "general merchandise", "clothing", "apparel", "shoe",
                  "footwear", "electronics", "electronic sales", "computer software stores", "computers computer peripheral",
                  "furniture", "home supply", "hardware", "sporting goods", "jewelry", "precious stones", "office supply",
                  "office and school supply", "stationery", "stationary", "household appliance", "music store", "record shops",
                  "toy", "gift", "florist", "pet shop", "pet store", "camera", "luggage", "craft", "hobby", "home furnish",
                  "house furnishing", "lumber", "nurseries", "garden", "miscellaneous and retail", "book stores", "books periodicals",
                  "news dealers", "automotive parts", "tire stores", "uniforms", "glass paint wallpaper", "sewing", "piece good",
                  "antique", "cosmetic", "used merchandise", "ready to wear", "accessory and speciality", "infant s wear",
                  "religious goods", "bicycle", "glassware", "stamp coin", "cigar", "wig", "fireplace", "tent and awning",
                  "swimming pools", "art dealers", "window covering", "motor vehicle supplies"]),
]


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip() + " "


_EXCL = [_norm(p).strip() for p in EXCLUDED]
_RULES = [(cat, [_norm(p).strip() if not p.startswith(" ") else " " + _norm(p).strip() for p in phrases]) for cat, phrases in MCC_RULES]


def map_mcc(desc: str) -> str | None:
    d = _norm(desc)
    if any(p in d for p in _EXCL):
        return None
    for cat, phrases in _RULES:
        if any(p in d for p in phrases):
            return cat
    return None


def merchant_group(descriptor: str) -> str:
    """Grouping key for leakage control: the first two alphabetic tokens (store numbers and locations removed)."""
    toks = [t for t in re.split(r"[^A-Z]+", str(descriptor).upper()) if len(t) >= 2]
    return " ".join(toks[:2]) or str(descriptor).upper()[:12]


def holder_hash(agency: str, last: str, initial: str) -> str:
    return hashlib.sha256(f"{PAN_PEPPER}|{agency}|{last}|{initial}".upper().encode()).hexdigest()[:16]


# the publisher renamed some columns between monthly files; these are the same fields
ALIASES = {"CH_LAST_NAME": "LAST_NAME", "FIRST_NAME": "FIRST_INITIAL", "MCC_DESCR": "MCC_DESCRIPTION"}


def _read(path: str, cols: list[str]) -> pd.DataFrame:
    head = pd.read_csv(path, nrows=0, encoding="latin-1")
    norm = {c: ALIASES.get(c.strip().upper().replace(" ", "_"), c.strip().upper().replace(" ", "_")) for c in head.columns}
    df = pd.read_csv(path, dtype=str, encoding="latin-1", on_bad_lines="skip").rename(columns=norm)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}; has {list(df.columns)}")
    return df[cols]


def load_oklahoma() -> tuple[pd.DataFrame, dict]:
    """All 48 monthly files (Jul 2020 - Jun 2024). Verified 2026-11-15: each calendar month is in exactly one file and no
    row appears in two files (the timestamped names are publication names, not republished copies). Identical rows WITHIN a
    file are kept: they are genuine repeat purchases (same person, merchant, amount, day). ROWID is absent from two files and
    is not used."""
    cols = ["AGENCYNBR", "LAST_NAME", "FIRST_INITIAL", "AMOUNT", "MERCHANT", "TRANSACTION_DATE", "POST_DATE", "MCC_DESCRIPTION",
            "CALENDAR_YEAR", "CALENDAR_MONTH"]
    files = sorted(glob.glob(str(RAW / "oklahoma_pcard" / "*.csv")))
    parts, per_file = [], {}
    for f in files:
        d = _read(f, cols)
        d["source_file"] = f.rsplit("/", 1)[1]
        per_file[d["source_file"].iloc[0] if len(d) else f] = int(len(d))
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    n0 = len(df)
    key = [c for c in cols]
    cross = df.duplicated(subset=key, keep=False) & (df.groupby(key, dropna=False)["source_file"].transform("nunique") > 1)
    if cross.any():                                   # a republished row: keep the first file's copy only
        df = df[~(cross & df.duplicated(subset=key, keep="first"))].copy()
    ym = df["CALENDAR_YEAR"].str.strip().astype(int) * 100 + df["CALENDAR_MONTH"].str.strip().astype(int)
    df["fiscal_year"] = (ym // 100) + ((ym % 100) >= 7).astype(int)          # Oklahoma FY runs July-June
    months_per_file = df.assign(ym=ym).groupby("source_file")["ym"].nunique()
    df["amount"] = pd.to_numeric(df["AMOUNT"], errors="coerce")
    df["date"] = pd.to_datetime(df["TRANSACTION_DATE"], format="%d-%b-%y", errors="coerce")
    df["holder"] = [holder_hash(a, l, i) for a, l, i in zip(df["AGENCYNBR"].str.strip(), df["LAST_NAME"].fillna(""), df["FIRST_INITIAL"].fillna(""))]
    df["merchant"] = df["MERCHANT"].fillna("").str.strip()
    df["mcc"] = df["MCC_DESCRIPTION"].fillna("").str.strip()
    out = df[["holder", "date", "amount", "merchant", "mcc", "fiscal_year"]]
    bad = out["date"].isna() | out["amount"].isna() | (out["merchant"] == "")
    rep = {"files": len(files), "rows_per_file": per_file, "rows": n0, "calendar_months": int(ym.nunique()),
           "months_in_more_than_one_file": int((df.assign(ym=ym).groupby("ym")["source_file"].nunique() > 1).sum()),
           "files_with_more_than_one_month": int((months_per_file > 1).sum()),
           "rows_repeated_across_files_dropped": int(n0 - len(df)),
           "rows_invalid_dropped": int(bad.sum()), "negative_amounts": int((out["amount"] < 0).sum()),
           "rows_by_fiscal_year": {int(k): int(v) for k, v in out["fiscal_year"].value_counts().sort_index().items()},
           "date_from": str(out["date"].min().date()), "date_to": str(out["date"].max().date())}
    return out[~bad].reset_index(drop=True), rep


def load_dc() -> tuple[pd.DataFrame, dict]:
    path = RAW / "dc_pcard" / "dc_purchase_card_transactions.csv"
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", usecols=["TRANSACTION_DATE", "TRANSACTION_AMOUNT", "VENDOR_NAME", "MCC_DESCRIPTION"])
    n0 = len(df)
    out = pd.DataFrame({"date": pd.to_datetime(df["TRANSACTION_DATE"].str[:10], format="%Y/%m/%d", errors="coerce"),
                        "amount": pd.to_numeric(df["TRANSACTION_AMOUNT"], errors="coerce"),
                        "merchant": df["VENDOR_NAME"].fillna("").str.strip(), "mcc": df["MCC_DESCRIPTION"].fillna("").str.strip()})
    bad = out["merchant"] == ""
    return out[~bad].reset_index(drop=True), {"rows": n0, "rows_without_vendor_dropped": int(bad.sum()),
                                               "date_from": str(out["date"].min().date()), "date_to": str(out["date"].max().date())}


def labelled(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map MCCs, report the mapping table, return rows with a Finora merchant category (one row per distinct descriptor+label)."""
    mapping = df.groupby("mcc").size().rename("rows").reset_index()
    mapping["finora_category"] = mapping["mcc"].map(map_mcc)
    d = df.assign(category=df["mcc"].map(dict(zip(mapping["mcc"], mapping["finora_category"]))))
    d = d[d["category"].notna()]
    d = d.assign(text=d["merchant"].str.upper().str.replace(r"\s+", " ", regex=True), group=d["merchant"].map(merchant_group))
    d = d.drop_duplicates(subset=["text", "category"])[["text", "category", "group"]]
    return d.reset_index(drop=True), mapping.sort_values("rows", ascending=False)

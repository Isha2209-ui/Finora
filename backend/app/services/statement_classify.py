"""Classify imported statement rows: spending category, income, transfer, refund, card payment - with a reason and a
confidence for every row, and a review flag wherever Finora is not sure.

Order of decisions (first match wins; every decision records who made it in `category_source`/`classified_by`):
  1. the person's own correction rules (a merchant they re-categorised before)             -> "user_rule"
  2. a category column in the file (e.g. a Finora export)                                   -> "given"
  3. structural rules that a text classifier cannot see:
       - money moving between the person's own accounts (own account/card last digits, SELF, OWN A/C, sweep,
         or an equal and opposite row in another of their accounts within 3 days)          -> Transfer
       - credit-card bill payments (bank side) and payments received (card side)           -> Card Payment
       - refunds / reversals / chargebacks, matched to the original purchase when possible -> refund of that category
       - salary (SALARY/PAYROLL wording, or the largest credit that arrives every month)    -> income: Salary
       - interest, dividends, cashback                                                       -> income
       - mutual-fund redemptions                                                             -> Investment (inflow)
  4. the trained Transaction Categoriser (TF-IDF + logistic regression) for every debit     -> "model", with its probability
  5. credits nobody recognised are NOT counted as income: they are kept as an incoming transfer and flagged for review,
     so a friend repaying a dinner never inflates income. Regular credits from the same sender are proposed as income.

Debits below 0.5 model confidence are flagged for review, the same threshold the categoriser uses everywhere else.
"""
from __future__ import annotations

import re


def _rx(pattern: str) -> re.Pattern:
    """Case-insensitive regex with all groups non-capturing (pandas warns about capturing groups in str.contains)."""
    return re.compile(re.sub(r"\((?!\?)", "(?:", pattern), re.I)

import numpy as np
import pandas as pd

from ..data.generator import DISCRETIONARY, ESSENTIAL, NON_EXPENSE
from ..ml import categoriser
from .cleaning import standardise_category

SPEND_CATEGORIES = sorted(ESSENTIAL | DISCRETIONARY | {"EMI", "Cash"})
INCOME_CLASSES = ["Salary", "Other income", "Interest", "Dividend", "Cashback & rewards", "Rental income", "Business income"]
REVIEW_THRESHOLD = 0.5
_STOP = set("""UPI DR CR NEFT IMPS RTGS POS ACH NACH ECS BIL BPAY ONL P2A P2M PAY PAID PAYMENT PAYMENTS TO FROM BY VIA REF
TRF TRANSFER TXN INB MOB MB NETBANK NET BANKING ONLINE RETAIL INDIA PVT LTD LIMITED PRIVATE TECHNOLOGIES SERVICES IN IND
INR RS THE AND FOR OF WITH GOOGLE GPAY PHONEPE PAYTM WALLET SENT USING YBL OKAXIS OKICICI OKSBI AXL IBL ICICI HDFC HDFCBANK
SBIN SBI ICIC UTIB AXIS KKBK KOTAK YESB YES BANK BARB PUNB IDFB CNRB AUTOPAY PAYU RAZ BIL MUM DEL BLR BANGALORE MUMBAI DELHI
JAIPUR PUNE GURGAON NOIDA HYDERABAD CHENNAI KOLKATA AHMEDABAD MERCHANT PURCHASE DEBIT CREDIT CARD XX REFNO NO DT
JAN FEB MAR APR MAY JUN JUL AUG SEP SEPT OCT NOV DEC JANUARY FEBRUARY MARCH APRIL JUNE JULY AUGUST SEPTEMBER OCTOBER
NOVEMBER DECEMBER MONTH MONTHLY REFUND REFUNDED RFND REVERSAL REVERSED CHARGEBACK RETURN CANCELLATION
""".split())
_VPA = re.compile(r"([A-Za-z0-9.\-_]+)@[A-Za-z]+")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_CARDMASK = re.compile(r"\b\d{4,6}X{4,}\d{2,4}\b", re.I)


def merchant_name(desc: str) -> str:
    """A stable, readable counterparty name from a raw narration ('UPI/DR/4029.../SWIGGY/YESB/swiggy@ybl' -> 'Swiggy')."""
    s = str(desc).upper()
    s = _VPA.sub(lambda m: " " + m.group(1).upper() + " ", s)
    s = _CARDMASK.sub(" ", _IFSC.sub(" ", s))
    toks = [t for t in re.split(r"[^A-Z&]+", s) if len(t) >= 2 and t not in _STOP]
    out: list[str] = []
    for t in toks:
        if not out or (t != out[-1] and not out[-1].startswith(t) and not t.startswith(out[-1])):
            out.append(t)
        if len(out) == 2:
            break
    return " ".join(out).title() if out else str(desc).strip()[:24].title()


# ---------------------------------------------------------------- structural patterns
SELF_TRF = _rx(r"\bself\b|own\s*(a/?c|acc|account)|\bsweep\b|to\s+own|trf\s+to\s+self|fd\s+(booking|creation)|\bmy\s+account\b")
CARD_BILL_DEBIT = _rx(r"credit\s*card|\bcc\s*(payment|pymt|bill)|card\s*(bill|payment)|\bcred\b|cardpay|bbps.*card")
CARD_PAYMENT_RECEIVED = _rx(r"payment\s*(received|recd|-\s*thank)|thank\s*you|\bautopay\b|bbps\s*payment|"
                                   r"(neft|imps|upi)\s*payment|payment\s+credit|\bpymt\s*recd|online\s*payment")
REFUND = _rx(r"\brefund|\brfnd\b|revers|\brev[\s\-:/]|chargeback|\breturn\b|cancell?ation\s*(credit|refund)")
CASHBACK = _rx(r"cash\s*back|\breward|\bpoints?\s*redeem")
SALARY = _rx(r"\bsalary\b|\bsal\b|\bsal[\s\-/]?(cr|credit|for)\b|payroll|\bwages?\b|stipend")
INTEREST = _rx(r"\binterest\b|\bint\.?\s*(pd|paid|cr|credit|earned)|\bsb\s*int|\bint\s+on\b|\bfd\s*int|\bcredit\s+interest")
DIVIDEND = _rx(r"\bdividend|\bdiv\b|\bach\s*c-.*div")
REDEMPTION = _rx(r"redemption|redeem|\bmf\s*red|\bsip\s*red|switch\s*out|\bcams\b.*cr|\bkfin|withdrawal\s*from\s*(mf|fund)")
RENT_IN = _rx(r"\brent\b")


def _last4_pattern(digits: set[str]) -> re.Pattern | None:
    d = sorted(x for x in digits if x and x.isdigit() and len(x) == 4)
    return re.compile(r"(?<!\d)(?:X{2,}|\*{2,}|x{2,})?(?:" + "|".join(d) + r")(?!\d)") if d else None


def predict_categories(art: dict, texts: pd.Series, progress=None, chunk: int = 5000) -> tuple[np.ndarray, np.ndarray]:
    """Run the categoriser once per distinct narration *shape* (digits collapsed) - statements repeat merchants with new
    reference numbers, so 150,000 rows usually collapse to a few thousand distinct texts."""
    keys = texts.map(categoriser.normalise)
    uniq = pd.unique(keys)
    first = pd.Series(texts.values, index=keys.values)
    first = first[~first.index.duplicated()]
    cats, confs = {}, {}
    for start in range(0, len(uniq), chunk):
        part = list(uniq[start:start + chunk])
        preds = categoriser.predict(art, [first[k] for k in part])
        for k, p in zip(part, preds):
            cats[k], confs[k] = p["category"], p["confidence"]
        if progress:
            progress(min(len(uniq), start + chunk), len(uniq))
    return keys.map(cats).values, keys.map(confs).values.astype(float), len(uniq)


def classify(rows: pd.DataFrame, *, kind: str, art: dict, rules: dict[str, str] | None = None,
             own_account_last4: set[str] | None = None, own_card_last4: set[str] | None = None,
             history: pd.DataFrame | None = None, this_account: tuple[str, int | None] = ("account", None),
             salary_months: set[str] | None = None, progress=None) -> tuple[pd.DataFrame, dict]:
    """Adds: merchant, category, category_source, confidence, needs_review, review_reason, flags, target ('tx'|'income'),
    income_source. Returns (rows, stats)."""
    t = rows.copy()
    n = len(t)
    rules = rules or {}
    t["merchant"] = t["raw_description"].map(merchant_name)
    t["mkey"] = t["merchant"].str.upper()
    model_cat, model_conf, n_unique = predict_categories(art, t["raw_description"], progress)
    t["model_category"], t["model_confidence"] = model_cat, model_conf
    t["category"] = None
    t["category_source"] = None
    t["confidence"] = np.nan
    t["needs_review"] = False
    t["review_reason"] = None
    t["flags"] = ""
    t["target"] = "tx"
    t["income_source"] = None
    is_cr = (t["type"] == "credit").values
    desc = t["raw_description"]
    own_acc = _last4_pattern(own_account_last4 or set())
    own_card = _last4_pattern(own_card_last4 or set())

    def setv(mask, **kw):
        mask = np.asarray(mask) & t["category_source"].isna().values
        for k, v in kw.items():
            t.loc[mask, k] = v
        return mask

    def add_flag(mask, flag):
        t.loc[mask, "flags"] = (t.loc[mask, "flags"] + "," + flag).str.strip(",")

    # 1. the person's own rules
    if rules:
        ruled = t["mkey"].map(rules)
        m = ruled.notna().values
        for cat in ruled[m].unique():
            mm = m & (ruled == cat).values
            if cat in INCOME_CLASSES:
                setv(mm & is_cr, target="income", income_source=cat, category=None, category_source="user_rule", confidence=1.0)
            else:
                setv(mm, category=cat, category_source="user_rule", confidence=1.0)
    # 2. a category column in the file
    if "category_given" in t and (t["category_given"].astype(str).str.len() > 0).any():
        given = t["category_given"].map(lambda c: standardise_category(c) if str(c).strip() else None)
        setv(given.notna().values, category=given, category_source="given", confidence=1.0)
    # 3a. own-account transfers and card bills
    own_mention = desc.str.contains(own_acc).values if own_acc is not None else np.zeros(n, bool)
    card_mention = desc.str.contains(own_card).values if own_card is not None else np.zeros(n, bool)
    if kind == "card":
        pm = setv(is_cr & (desc.str.contains(CARD_PAYMENT_RECEIVED).values | own_mention) & ~desc.str.contains(REFUND).values,
                  category="Card Payment", category_source="rule:card_payment_received", confidence=0.95)
        add_flag(pm, "card_payment")
    else:
        cb = setv(~is_cr & (desc.str.contains(CARD_BILL_DEBIT).values | card_mention),
                  category="Card Payment", category_source="rule:card_bill_payment", confidence=0.95)
        add_flag(cb, "card_payment")
        st = setv(desc.str.contains(SELF_TRF).values | own_mention, category="Transfer", category_source="rule:own_account_transfer",
                  confidence=0.95)
        add_flag(st, "transfer")
        if history is not None and len(history):
            paired = _pair_transfers(t, history, this_account)
            st2 = setv(paired, category="Transfer", category_source="rule:matched_own_account_transfer", confidence=0.9)
            add_flag(st2, "transfer")
    # 3b. refunds (credits that give back a purchase)
    refund_kw = is_cr & desc.str.contains(REFUND).values
    card_credit_other = is_cr & (kind == "card") & ~desc.str.contains(CASHBACK).values
    ref_cat = _match_refunds(t, history)
    rf = refund_kw | (card_credit_other & t["category_source"].isna().values)
    cat_for_refund = pd.Series(np.where(pd.notna(ref_cat), ref_cat, t["model_category"]), index=t.index)
    cat_for_refund = cat_for_refund.where(cat_for_refund.isin(SPEND_CATEGORIES), "Shopping")
    matched = pd.notna(ref_cat)
    m1 = setv(rf & matched, category=cat_for_refund, category_source="rule:refund_matched", confidence=0.9)
    m2 = setv(rf & ~matched, category=cat_for_refund, category_source="rule:refund", confidence=0.6)
    add_flag(m1 | m2, "refund")
    t.loc[m2, "needs_review"] = True
    t.loc[m2, "review_reason"] = "Refund whose original purchase was not found; its category is the model's best guess."
    # 3c. income on bank statements
    if kind != "card":
        setv(is_cr & desc.str.contains(SALARY).values, target="income", income_source="Salary", category_source="rule:salary_wording",
             confidence=0.95)
        setv(is_cr & desc.str.contains(INTEREST).values, target="income", income_source="Interest", category_source="rule:interest",
             confidence=0.95)
        setv(is_cr & desc.str.contains(DIVIDEND).values, target="income", income_source="Dividend", category_source="rule:dividend",
             confidence=0.9)
        inv = setv(is_cr & desc.str.contains(REDEMPTION).values, category="Investment", category_source="rule:investment_redemption",
                   confidence=0.85)
        add_flag(inv, "investment_inflow")
    setv(is_cr & desc.str.contains(CASHBACK).values, target="income" if kind != "card" else "tx",
         income_source="Cashback & rewards" if kind != "card" else None,
         category=None if kind != "card" else "Shopping", category_source="rule:cashback", confidence=0.8)
    # 3d. regular credits: the largest steady monthly credit is salary; other steady credits are proposed income
    if kind != "card":
        _regular_credits(t, setv, salary_months)
    # 4. the categoriser for every remaining debit
    deb = ~is_cr
    mm = setv(deb, category=t["model_category"], category_source="model", confidence=t["model_confidence"])
    low = mm & (t["model_confidence"] < REVIEW_THRESHOLD).values
    t.loc[low, "needs_review"] = True
    t.loc[low, "review_reason"] = [f"Model is only {c:.0%} sure this is {k}." for c, k in
                                   zip(t.loc[low, "model_confidence"], t.loc[low, "model_category"])]
    # 5. unrecognised credits: kept out of income until confirmed
    rest = setv(is_cr, category="Transfer", category_source="rule:unrecognised_credit", confidence=0.3)
    t.loc[rest, "needs_review"] = True
    t.loc[rest, "review_reason"] = "Credit from a sender Finora does not recognise. It is not counted as income until you confirm what it is."
    add_flag(rest, "unrecognised_credit")
    # investment debits are investment cash flows (SIPs, lump sums) - never treated as holdings
    add_flag((t["category"] == "Investment").values & ~is_cr, "investment_outflow")
    t.loc[t["target"] == "income", "category"] = None
    stats = {"rows": n, "distinct_narrations_scored": int(n_unique),
             "by_source": t["category_source"].str.split(":").str[0].value_counts().to_dict(),
             "needs_review": int(t["needs_review"].sum())}
    return t.drop(columns=["mkey"]), stats


def _regular_credits(t: pd.DataFrame, setv, salary_months: set[str] | None = None) -> None:
    cand = t[(t["type"] == "credit") & t["category_source"].isna()]
    if cand.empty:
        return
    cand = cand.assign(month=cand["date"].dt.to_period("M"))
    groups = []
    for mk, g in cand.groupby("mkey"):
        monthly = g.groupby("month")["amount"].sum()
        if len(monthly) < 3 or monthly.median() < 5000:
            continue
        cv = float(monthly.std(ddof=0) / monthly.mean()) if monthly.mean() else 9
        per_month = len(g) / len(monthly)
        if cv <= 0.25 and per_month <= 1.5:
            groups.append((monthly.median(), mk, cv, len(monthly), {str(m) for m in monthly.index}))
    groups.sort(reverse=True)
    salary_months = salary_months or set()
    for i, (med, mk, cv, months, mset) in enumerate(groups):
        mask = ((t["mkey"] == mk) & (t["type"] == "credit")).values
        overlaps_salary = bool(mset & salary_months)
        if i == 0 and med >= 10000 and not (t["income_source"] == "Salary").any() and not overlaps_salary:
            setv(mask, target="income", income_source="Salary", category_source="rule:regular_monthly_credit",
                 confidence=0.85 if cv <= 0.1 else 0.7)
            if cv > 0.1:
                t.loc[mask & (t["category_source"] == "rule:regular_monthly_credit").values, "needs_review"] = True
                t.loc[mask & (t["category_source"] == "rule:regular_monthly_credit").values, "review_reason"] = (
                    f"Arrives every month ({months} months) so it was treated as salary, but the amount varies; please confirm.")
        else:
            src = "Rental income" if t.loc[mask, "raw_description"].str.contains(RENT_IN).any() else "Other income"
            m = setv(mask, target="income", income_source=src, category_source="rule:regular_credit", confidence=0.6)
            t.loc[m, "needs_review"] = True
            who = t.loc[m, 'merchant'].iloc[0] if m.any() else 'one sender'
            t.loc[m, "review_reason"] = (f"Regular credit from {who} in {months} months, in months that already have a salary recorded: "
                                         "counted as other income, not a second salary; please confirm." if overlaps_salary and i == 0 else
                                         f"Regular credit from {who} in {months} months: counted as income; please confirm.")


PAIR_MAX_MODEL_CONFIDENCE = 0.6


def _pair_transfers(t: pd.DataFrame, history: pd.DataFrame, this_account) -> np.ndarray:
    """A row is a self-transfer when an equal and opposite row sits in ANOTHER of the person's accounts within 3 days
    AND there is evidence on both sides: the other row is already a transfer, and this row is not something the model
    confidently recognises as a purchase or income (amount and date alone are a coincidence, e.g. a Rs 600 Swiggy order
    on the day a friend sent Rs 600)."""
    field, ident = this_account
    # evidence = a RECOGNISED transfer (rule, file or the person). An unrecognised credit is only parked as "Transfer"
    # pending review, so it is never evidence.
    h = history[(history["category"] == "Transfer") & (history["category_source"].fillna("") != "rule:unrecognised_credit")] \
        if {"category", "category_source"} <= set(history.columns) else history.iloc[0:0]
    if field == "account":
        h = h[(h["account_id"].notna()) & (h["account_id"] != ident)]
    else:
        h = h[h["account_id"].notna()]
    if h.empty:
        return np.zeros(len(t), bool)
    hd = pd.to_datetime(h["date"])
    index: dict[tuple[float, str], list] = {}
    for d, a, ty in zip(hd, h["amount"].round(2), h["type"]):
        index.setdefault((float(a), ty), []).append(d)            # each twin can be used once (one-to-one)
    out = np.zeros(len(t), bool)
    # debits: not something the model confidently sees as a purchase. Credits: the model only knows spending narrations,
    # so its guess says nothing about a credit; the other side already being a transfer is the evidence.
    eligible = ((t["type"] == "credit") | t["model_category"].isin(["Transfer", "Card Payment"])
                | (t["model_confidence"] < PAIR_MAX_MODEL_CONFIDENCE)).values
    for i, (d, a, ty) in enumerate(zip(t["date"], t["amount"].round(2), t["type"])):
        if not eligible[i]:
            continue
        opp = "debit" if ty == "credit" else "credit"
        twins = index.get((float(a), opp), [])
        for j, hd_ in enumerate(twins):
            if abs((hd_ - d).days) <= 3:
                out[i] = True
                twins.pop(j)
                break
    return out


def _match_refunds(t: pd.DataFrame, history: pd.DataFrame | None) -> np.ndarray:
    """For each credit, the category of an earlier purchase from the same merchant (within 90 days, amount >= refund)."""
    deb = t[t["type"] == "debit"][["date", "amount", "mkey", "model_category"]].rename(columns={"model_category": "cat"})
    if history is not None and len(history):
        h = history[history["type"] == "debit"]
        if len(h):
            deb = pd.concat([deb, pd.DataFrame({"date": pd.to_datetime(h["date"]), "amount": h["amount"],
                                                "mkey": h["raw_description"].map(merchant_name).str.upper(), "cat": h["category"]})])
    out = np.full(len(t), None, dtype=object)
    if deb.empty:
        return out
    by_m = {k: g.sort_values("date") for k, g in deb.groupby("mkey")}
    for i, (d, a, ty, mk) in enumerate(zip(t["date"], t["amount"], t["type"], t["mkey"])):
        if ty != "credit" or mk not in by_m:
            continue
        g = by_m[mk]
        win = g[(g["date"] <= d) & (g["date"] >= d - pd.Timedelta(days=90)) & (g["amount"] >= a - 0.5)]
        if len(win) and win["cat"].iloc[-1] in SPEND_CATEGORIES:
            out[i] = win["cat"].iloc[-1]
    return out

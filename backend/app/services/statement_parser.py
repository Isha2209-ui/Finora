"""Statement file reader: detects the layout of a bank or card statement CSV and turns it into clean rows.

What it handles (each is covered by tests in tests/test_statement_import.py):
  * encodings: UTF-8 (with or without BOM), UTF-16 (BOM), Windows-1252
  * delimiters: comma, semicolon, tab, pipe
  * bank header junk above the real header row, and summary/footer lines below the data
  * column roles found by name in any order: date, value date, narration, debit, credit, single amount,
    Dr/Cr indicator, running balance, reference / cheque number, category
  * amounts like "1,23,456.78", "Rs. 500", "₹500", "(500.00)", "500-", "500.00 Cr", "500 DR"
  * date formats: DD/MM/YYYY, DD-MM-YY, YYYY-MM-DD, "05 Oct 2026", "05-Oct-26", with or without a time;
    the format is chosen from the data itself (day-first is preferred only when the data cannot tell)
  * newest-first statements (rows are put into date order, keeping the order of same-day rows)
  * running balances: every row is reconciled against the previous balance; the closing balance is reported as
    "verified" only when the chain reconciles

Nothing here invents data. A row without a valid date or amount is dropped and counted with its reason.
Named layouts ("resembles HDFC-style export") are labels inferred from column headers only. The mapping itself is
generic, so an unknown bank works as long as its columns can be recognised (or are mapped by the person).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import STATEMENT_MAX_ROWS as MAX_ROWS  # noqa: E402  (read again at call time below)
CHUNK = 10_000

ROLES = ["date", "value_date", "description", "debit", "credit", "amount", "drcr", "balance", "ref", "category"]
SYNONYMS: dict[str, list[str]] = {
    "date": ["date", "txn date", "transaction date", "tran date", "trans date", "posting date", "post date", "booking date",
             "transaction posted date", "entry date"],
    "value_date": ["value date", "value dt", "val date"],
    "description": ["description", "narration", "particulars", "details", "transaction details", "remarks", "transaction remarks",
                    "transaction description", "merchant", "merchant name", "payee", "description narration", "transaction particulars"],
    "debit": ["debit", "withdrawal", "withdrawals", "withdrawal amt", "withdrawal amount", "debit amount", "dr amount", "dr",
              "debits", "money out", "paid out", "debit amt"],
    "credit": ["credit", "deposit", "deposits", "deposit amt", "deposit amount", "credit amount", "cr amount", "cr", "credits",
               "money in", "paid in", "credit amt"],
    "amount": ["amount", "transaction amount", "amt", "txn amount", "amount inr", "billing amount", "amount in rs", "value"],
    "drcr": ["dr cr", "cr dr", "type", "txn type", "transaction type", "debit credit", "dr cr indicator", "d c"],
    "balance": ["balance", "closing balance", "running balance", "available balance", "bal", "balance amount", "closing bal"],
    "ref": ["ref no", "reference", "reference no", "ref", "chq ref no", "cheque no", "cheque number", "chq no", "chqno",
            "ref no cheque no", "chq ref number", "utr", "transaction id", "reference number"],
    "category": ["category"],
}
# Layout labels (header fingerprints). Only used to name what was detected; parsing never depends on them.
LAYOUTS = [
    ("HDFC-style savings export", {"date", "narration", "chq ref no", "value dt", "withdrawal amt", "deposit amt", "closing balance"}),
    ("ICICI-style savings export", {"value date", "transaction date", "transaction remarks", "withdrawal amount", "deposit amount", "balance"}),
    ("SBI-style savings export", {"txn date", "value date", "description", "ref no cheque no", "debit", "credit", "balance"}),
    ("Axis-style savings export", {"tran date", "particulars", "dr", "cr", "bal"}),
    ("Kotak-style export (amount + Dr/Cr)", {"description", "amount", "dr cr", "balance"}),
    ("Card statement (amount with Cr/Dr marks)", {"date", "transaction details", "amount"}),
    ("Finora transactions export", {"date", "description", "amount", "type", "category"}),
]
DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%Y/%m/%d",
                "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%d %b %y", "%d-%b-%y", "%d %B %Y", "%b %d, %Y", "%b %d %Y",
                "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y%m%d"]
OPENING_ROW = re.compile(r"\b(?:opening|closing)\s+balance\b|^\s*b/?f\b|brought forward|carried forward|^\s*total\b", re.I)


class StatementError(ValueError):
    """A problem the person can fix (shown to them as-is)."""


@dataclass
class Parsed:
    rows: pd.DataFrame                      # date, raw_description, amount, type, balance, ref, category_given, file_line
    detection: dict = field(default_factory=dict)


# ---------------------------------------------------------------- text & table
def decode(content: bytes) -> tuple[str, str]:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16"), "utf-16"
    try:
        return content.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace"), "windows-1252"


def norm_header(h: str) -> str:
    h = str(h).lower().replace("₹", " ").replace("(inr)", " ").replace("inr", " ").replace("rs.", " ")
    h = re.sub(r"[^a-z0-9]+", " ", h)
    h = re.sub(r"\b(in|rs|inr)\b", " ", h)                 # "Amount (in Rs.)" -> "amount"
    return re.sub(r"\s+", " ", h).strip()


def _role_of(h: str) -> str | None:
    n = norm_header(h)
    if not n:
        return None
    for role in ROLES:                                  # exact names first
        if n in SYNONYMS[role]:
            return role
    for role in ("value_date", "balance", "debit", "credit", "description", "date", "amount", "ref"):  # then "contains"
        for syn in SYNONYMS[role]:
            if len(syn) > 3 and re.search(rf"\b{re.escape(syn)}\b", n):
                return role
    return None


def _split(line: str, delim: str) -> list[str]:
    return next(csv.reader([line], delimiter=delim))


def find_header(lines: list[str]) -> tuple[int, str, list[str]]:
    """The header row is the line (within the first 60) whose cells name the most known roles."""
    best = (-1, 0, ",", [])
    for i, line in enumerate(lines[:60]):
        if not line.strip():
            continue
        for delim in [",", ";", "\t", "|"]:
            if delim not in line:
                continue
            try:
                cells = _split(line, delim)
            except csv.Error:
                continue
            roles = {_role_of(c) for c in cells} - {None}
            ok = "date" in roles and "description" in roles and ({"amount", "debit", "credit"} & roles)
            score = len(roles) + (10 if ok else 0)
            if score > best[0]:
                best = (score, i, delim, cells)
    if best[0] >= 10:
        return best[1], best[2], best[3]
    # No recognisable header: use the first line with at least 3 columns (whose next line has the same width) and let the
    # person map the columns themselves.
    for i, line in enumerate(lines[:60]):
        for delim in [",", ";", "\t", "|"]:
            cells = _split(line, delim) if delim in line else []
            nxt = next((l for l in lines[i + 1:i + 5] if l.strip()), "")
            if len(cells) >= 3 and all(c.strip() for c in cells) and nxt and len(_split(nxt, delim)) == len(cells):
                return i, delim, cells
    raise StatementError("Could not find a header row: a statement needs a header line with at least a date, a description "
                         "and an amount (or debit/credit) column in the first 60 lines.")


def auto_mapping(headers: list[str]) -> dict[str, int]:
    """role -> column index. A second Dr/Cr column right after the balance column is the balance's own sign."""
    mapping: dict[str, int] = {}
    for idx, h in enumerate(headers):
        role = _role_of(h)
        if role is None:
            continue
        if role == "drcr" and "drcr" in mapping and mapping.get("balance") == idx - 1:
            mapping["balance_drcr"] = idx
            continue
        if role == "date" and "date" in mapping:
            continue
        mapping.setdefault(role, idx)
    # a lone "dr"/"cr" pair of amount columns (Axis style) is debit/credit, not an indicator
    if "date" not in mapping and "value_date" in mapping:
        mapping["date"] = mapping.pop("value_date")
    return mapping


def layout_name(headers: list[str]) -> str:
    hs = {norm_header(h) for h in headers}
    best, score = "Generic statement layout", 0.0
    for name, fp in LAYOUTS:
        s = len(fp & hs) / len(fp)
        if s > score and s >= 0.85:
            best, score = name, s
    return best


# ---------------------------------------------------------------- values
_AMT_SUFFIX = re.compile(r"(?i)\s*\b(cr|dr)\b\.?\s*$")


def parse_amounts(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Returns (signed float amount, 'cr'/'dr'/None mark). Unparseable -> NaN."""
    s = s.fillna("").astype(str).str.strip()
    mark = s.str.extract(_AMT_SUFFIX, expand=False).str.lower()
    v = s.str.replace(_AMT_SUFFIX, "", regex=True)
    neg = v.str.contains(r"^\(.*\)$|-\s*$|^-", regex=True)
    v = v.str.replace(r"(?i)inr|rs\.?|₹|[,\s()]", "", regex=True).str.replace(r"-$", "", regex=True).str.lstrip("-").str.lstrip("+")
    num = pd.to_numeric(v.where(v.str.match(r"^\d*\.?\d+$")), errors="coerce")
    num = num.where(~neg, -num)
    return num, mark.where(mark.isin(["cr", "dr"]), None)


def infer_date_format(values: pd.Series) -> str | None:
    sample = values.dropna().astype(str).str.strip()
    sample = sample[sample != ""].head(800)
    if sample.empty:
        return None
    stripped = sample.str.replace(r"[ T]\d{1,2}:\d{2}(:\d{2})?(\s*[AP]M)?$", "", regex=True)
    best, best_rate = None, 0.0
    for fmt in DATE_FORMATS:
        rate = pd.to_datetime(stripped, format=fmt, errors="coerce").notna().mean()
        if rate > best_rate + 1e-9:            # strictly better: day-first formats come first, so they win ties
            best, best_rate = fmt, rate
    return best if best_rate >= 0.5 else None


def parse_dates(values: pd.Series, fmt: str | None) -> pd.Series:
    v = values.fillna("").astype(str).str.strip().str.replace(r"[ T]\d{1,2}:\d{2}(:\d{2})?(\s*[AP]M)?$", "", regex=True)
    if fmt:
        return pd.to_datetime(v, format=fmt, errors="coerce")
    return pd.to_datetime(v, errors="coerce", dayfirst=True, format="mixed")


# ---------------------------------------------------------------- unquoted thousands separators
_GROUPED = re.compile(r"^[-(]?(?:₹|Rs\.?\s*)?(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+)(?:\.\d+)?\)?(?:\s*(?:Cr|Dr|CR|DR))?$")


def repair_split_numbers(cells: list[str], width: int, start: int) -> list[str] | None:
    """A comma-delimited export that writes 1,23,456.78 without quotes splits one amount into several cells. Re-join
    fragments to the right of the description only when the joined text is a correctly grouped number (Indian 1,23,456
    or Western 123,456) and exactly ONE way of doing so gives the header's width. Otherwise the row stays rejected."""
    extra = len(cells) - width
    sols: list[list[str]] = []

    def dfs(i: int, cur: list[str], remaining: int) -> None:
        if len(sols) > 1:
            return
        if i == len(cells):
            if remaining == 0:
                sols.append(cur)
            return
        if len(cells) - i < remaining:
            return
        dfs(i + 1, cur + [cells[i]], remaining)
        for m in range(1, remaining + 1):
            if i + m >= len(cells):
                break
            joined = ",".join(c.strip() for c in cells[i:i + m + 1])
            if _GROUPED.match(joined):
                dfs(i + m + 1, cur + [joined], remaining - m)

    dfs(start, list(cells[:start]), extra)
    return sols[0] if len(sols) == 1 else None


# ---------------------------------------------------------------- main entry
def read_table(content: bytes, max_rows: int | None = None) -> dict:
    max_rows = MAX_ROWS if max_rows is None else max_rows
    text, enc = decode(content)
    lines = text.splitlines()
    hdr_idx, delim, headers = find_header(lines)
    body = [l for l in lines[hdr_idx + 1:]]
    n_data = sum(1 for l in body if l.strip())
    if n_data > max_rows:
        raise StatementError(f"This file has {n_data:,} data rows; the limit is {max_rows:,}. Split it into smaller files "
                             "(for example one per year) and import them one after another.")
    rows, bad_width, repaired, lines_no = [], 0, 0, []
    reader = csv.reader(body, delimiter=delim)
    width = len(headers)
    desc_idx = auto_mapping(headers).get("description", 0)
    for offset, cells in enumerate(reader):
        if not any(c.strip() for c in cells):
            continue
        if len(cells) < width:
            cells = cells + [""] * (width - len(cells))
        elif len(cells) > width:
            if not any(c.strip() for c in cells[width:]):
                cells = cells[:width]
            else:
                fixed = repair_split_numbers(cells, width, desc_idx + 1) if delim == "," else None
                if fixed is None:
                    bad_width += 1
                    continue
                cells, repaired = fixed, repaired + 1
        rows.append(cells)
        lines_no.append(hdr_idx + 2 + offset)
    return {"encoding": enc, "delimiter": {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}[delim],
            "header_line": hdr_idx + 1, "headers": headers, "rows": rows, "file_lines": lines_no,
            "rows_wrong_width": bad_width, "rows_repaired": repaired, "layout": layout_name(headers)}


def missing_roles(mapping: dict) -> list[str]:
    miss = [r for r in ("date", "description") if r not in mapping]
    if not ({"amount", "debit", "credit"} & set(mapping)):
        miss.append("amount (or debit/credit)")
    return miss


def detect(content: bytes, sample_rows: int | None = None, return_rows: bool = False):
    """Preview: layout, mapping, date format, sign convention, the WHOLE file's balance check and sample rows.
    The full file is parsed (not a sample) so the closing balance shown is the file's real last balance."""
    t = read_table(content)
    mapping = auto_mapping(t["headers"])
    if missing_roles(mapping):
        det = {"needs_mapping": True, "missing": missing_roles(mapping), "layout": "Unrecognised layout", "headers": t["headers"],
               "mapping": {r: t["headers"][i] for r, i in mapping.items()}, "mapping_index": mapping, "encoding": t["encoding"],
               "delimiter": t["delimiter"], "header_line": t["header_line"], "rows_in_file": len(t["rows"]),
               "raw_sample": t["rows"][:8], "suggested_kind": "bank", "warnings": [], "dropped": {},
               "balance": {"present": "balance" in mapping}}
        return (det, None) if return_rows else det
    sub = {**t, "rows": t["rows"][:sample_rows], "file_lines": t["file_lines"][:sample_rows]} if sample_rows else t
    parsed = parse(sub, mapping=mapping, kind=None)
    det = parsed.detection
    det["rows_in_file"] = len(t["rows"])
    det["sample"] = [{"date": r.date.isoformat()[:10], "description": r.raw_description[:90], "amount": round(r.amount, 2), "type": r.type,
                      "balance": None if pd.isna(r.balance) else round(r.balance, 2)} for r in parsed.rows.head(8).itertuples()]
    return (det, parsed.rows) if return_rows else det


def parse(table: dict, mapping: dict[str, int] | None = None, kind: str | None = "bank", sign: str | None = None,
          date_format: str | None = None, progress=None) -> Parsed:
    """Turn the raw table into clean rows. `kind` = bank | card | None (guess); `sign` = negative_is_debit | positive_is_debit."""
    headers, raw = table["headers"], table["rows"]
    mapping = dict(mapping or auto_mapping(headers))
    for role in ("date", "description"):
        if role not in mapping:
            raise StatementError(f"No column is mapped to '{role.replace('_', ' ')}'. Columns found: {', '.join(headers)}")
    if not ({"amount", "debit", "credit"} & set(mapping)):
        raise StatementError("No amount column (or debit/credit columns) is mapped. Columns found: " + ", ".join(headers))
    df = pd.DataFrame(raw, columns=range(len(headers)), dtype=str) if raw else pd.DataFrame(columns=range(len(headers)), dtype=str)
    col = lambda role: df[mapping[role]] if role in mapping else None  # noqa: E731
    dfmt = date_format or infer_date_format(col("date"))
    n = len(df)
    dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    for start in range(0, max(n, 1), CHUNK):                       # chunked so progress can be reported on large files
        sl = slice(start, start + CHUNK)
        dates.iloc[sl] = parse_dates(col("date").iloc[sl], dfmt)
        if progress:
            progress(min(n, start + CHUNK), n)
    desc = col("description").fillna("").astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    warnings: list[str] = []
    # ---- direction & amount
    if "debit" in mapping or "credit" in mapping:
        deb = parse_amounts(col("debit"))[0].abs() if "debit" in mapping else pd.Series(np.nan, index=df.index)
        cre = parse_amounts(col("credit"))[0].abs() if "credit" in mapping else pd.Series(np.nan, index=df.index)
        both = (deb.fillna(0) > 0) & (cre.fillna(0) > 0)
        if both.any():
            warnings.append(f"{int(both.sum())} rows had both a debit and a credit; the net amount was used.")
        net = (cre.fillna(0) - deb.fillna(0)).where(deb.notna() | cre.notna())   # both blank/unreadable -> no amount
        amount, typ, layout_kind = net.abs(), np.where(net > 0, "credit", "debit"), "separate debit and credit columns"
        sign_used = None
    else:
        amt, mark = parse_amounts(col("amount"))
        if "drcr" in mapping:
            ind = col("drcr").fillna("").astype(str).str.strip().str.lower()
            is_cr = ind.str.match(r"^(c|cr|credit|deposit)")
            typ = np.where(is_cr, "credit", "debit")   # anything not marked as a credit is a debit
            amount, layout_kind, sign_used = amt.abs(), "amount with a Dr/Cr column", None
        elif mark.notna().any() and (amt.dropna() >= 0).all():    # e.g. "1,200.00 Cr" on card statements
            typ = np.where(mark == "cr", "credit", "debit")          # unmarked lines on such statements are debits
            amount, layout_kind, sign_used = amt.abs(), "amount with Cr/Dr marks", None
        else:
            sign_used = sign
            amount, layout_kind = amt.abs(), "signed amount"
            if sign_used is None:
                sign_used = _infer_sign(amt, col("balance"), mapping, kind)
            typ = np.where(amt < 0, "debit", "credit") if sign_used == "negative_is_debit" else np.where(amt < 0, "credit", "debit")
    balance = None
    if "balance" in mapping:
        balance, bmark = parse_amounts(col("balance"))
        if "balance_drcr" in mapping:
            bmark = col("balance_drcr").fillna("").astype(str).str.strip().str.lower().str[:2]
        balance = balance.where(~(bmark.fillna("").str.startswith("dr")), -balance.abs())
    out = pd.DataFrame({"date": dates, "raw_description": desc, "amount": amount.astype(float), "type": typ,
                        "balance": balance.astype(float) if balance is not None else np.nan,
                        "ref": col("ref").fillna("").astype(str).str.strip() if "ref" in mapping else "",
                        "category_given": col("category").fillna("").astype(str).str.strip() if "category" in mapping else "",
                        "file_line": table["file_lines"][:n]})
    # ---- drop what is not a transaction, counting why
    dropped: dict[str, int] = {}

    def drop(mask, reason):
        k = int(mask.sum())
        if k:
            dropped[reason] = dropped.get(reason, 0) + k
        return out[~mask]

    if table.get("rows_wrong_width"):
        dropped["wrong number of columns"] = table["rows_wrong_width"]
    out = drop(out["raw_description"].str.contains(OPENING_ROW) & (out["amount"].fillna(0) == 0), "opening/closing balance line")
    out = drop(out["date"].isna(), "no valid date (summary or footer line)")
    out = drop(out["amount"].isna(), "no valid amount")
    out = drop(out["amount"] == 0, "zero amount")
    out = drop(out["raw_description"].str.len() < 2, "no description")
    # ---- chronological order (statements are often newest first); same-day rows keep file order
    order = "oldest first"
    if len(out) > 1 and out["date"].iloc[0] > out["date"].iloc[-1]:
        out = out.iloc[::-1]
        order = "newest first"
    out = out.reset_index(drop=True)
    out = out.iloc[np.argsort(out["date"].values, kind="stable")].reset_index(drop=True)
    bal = reconcile(out) if balance is not None else {"present": False}
    dates_ok = out["date"]
    det = {"layout": table.get("layout"), "layout_kind": layout_kind, "encoding": table.get("encoding"),
           "delimiter": table.get("delimiter"), "header_line": table.get("header_line"), "headers": headers,
           "mapping": {r: headers[i] for r, i in mapping.items()}, "mapping_index": mapping, "date_format": dfmt,
           "sign_convention": sign_used, "file_order": order, "rows_parsed": int(n), "rows_valid": int(len(out)),
           "dropped": dropped, "warnings": warnings, "balance": bal,
           "date_from": dates_ok.min().date().isoformat() if len(out) else None,
           "date_to": dates_ok.max().date().isoformat() if len(out) else None,
           "months_covered": int(dates_ok.dt.to_period("M").nunique()) if len(out) else 0,
           "debits": int((out["type"] == "debit").sum()), "credits": int((out["type"] == "credit").sum()),
           "suggested_kind": guess_kind(out, mapping, headers)}
    if table.get("rows_repaired"):
        warnings.append(f"{table['rows_repaired']:,} rows had amounts written without quotes (1,234.00 in a comma-separated file); "
                        "they were re-joined only where exactly one reading fits the columns.")
    if not dfmt:
        warnings.append("The date format could not be pinned down from the data; dates were read day-first.")
    return Parsed(out, det)


def _infer_sign(amt: pd.Series, bal_col, mapping, kind) -> str:
    """For a single signed amount column: use the running balance to decide which sign is a debit, else the convention
    of the statement kind (bank exports show money out as negative; card statements show spends as positive)."""
    if bal_col is not None:
        bal = parse_amounts(bal_col)[0]
        ok = amt.notna() & bal.notna()
        a, b = amt[ok].values, bal[ok].values
        if len(a) > 2:
            # file order may be oldest- or newest-first; test both directions
            fwd, rev = np.diff(b), -np.diff(b)
            neg_is_debit = max(np.mean(np.isclose(fwd, a[1:], atol=0.51)), np.mean(np.isclose(rev, a[:-1], atol=0.51)))
            pos_is_debit = max(np.mean(np.isclose(fwd, -a[1:], atol=0.51)), np.mean(np.isclose(rev, -a[:-1], atol=0.51)))
            if max(neg_is_debit, pos_is_debit) >= 0.6:
                return "negative_is_debit" if neg_is_debit >= pos_is_debit else "positive_is_debit"
    if kind == "card":
        return "positive_is_debit"
    neg_share = (amt < 0).mean()
    return "negative_is_debit" if neg_share > 0 or kind == "bank" else "positive_is_debit"


def reconcile(rows: pd.DataFrame, tol: float = 0.51) -> dict:
    """Check every running balance against the previous one +/- the amount. The closing balance is 'verified' only if
    (almost) the whole chain reconciles and the last rows do; otherwise it is reported but not trusted."""
    b = rows["balance"]
    has = b.notna()
    if has.sum() < 2:
        return {"present": bool(has.any()), "verified": False, "checked": 0,
                "reason": "Fewer than two rows carry a running balance, so nothing can be reconciled."}
    sub = rows[has]
    signed = np.where(sub["type"] == "credit", sub["amount"], -sub["amount"])
    expected = sub["balance"].shift(1) + signed
    good = (expected - sub["balance"]).abs() <= tol
    good = good.iloc[1:]
    checked, ok = int(len(good)), int(good.sum())
    tail_ok = bool(good.tail(min(10, len(good))).all())
    pct = ok / checked * 100 if checked else 0.0
    breaks = [{"file_line": int(sub["file_line"].iloc[i + 1]), "date": sub["date"].iloc[i + 1].date().isoformat()}
              for i, g in enumerate(good.values) if not g][:10]
    last = sub.iloc[-1]
    verified = pct >= 98.0 and tail_ok
    opening = float(sub["balance"].iloc[0] - signed[0])
    return {"present": True, "checked": checked, "reconciled": ok, "reconciled_pct": round(pct, 2), "verified": verified,
            "closing_balance": round(float(last["balance"]), 2), "closing_date": last["date"].date().isoformat(),
            "opening_balance": round(opening, 2), "breaks": breaks, "rows_with_balance": int(has.sum()),
            "reason": None if verified else (f"Only {pct:.1f}% of running balances reconcile with the amounts, so the closing balance "
                                             "is not treated as verified." if pct < 98 else
                                             "The last rows do not reconcile, so the closing balance is not treated as verified.")}


CARD_HINTS = re.compile(r"(?i)payment received|thank you|cashback|reward|emi conversion|finance charge|late fee|gst on")


def guess_kind(rows: pd.DataFrame, mapping: dict, headers: list[str]) -> str:
    """bank if there is a running balance or salary-like credits; card if card-statement wording dominates."""
    if "balance" in mapping:
        return "bank"
    text = " ".join(rows["raw_description"].head(400).tolist())
    card_score = len(CARD_HINTS.findall(text))
    credit_share = (rows["type"] == "credit").mean() if len(rows) else 0
    return "card" if card_score >= 1 and credit_share < 0.25 else "bank"

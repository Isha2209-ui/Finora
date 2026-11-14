"""Download the approved REAL datasets, unchanged, with provenance.

    python -m app.ml.data.acquire                # all approved datasets
    python -m app.ml.data.acquire scf moneyvis   # some of them

Each dataset lands in datasets/raw/<key>/ exactly as published, next to SOURCE.json:
publisher, page URL, download URLs, licence (as stated by the publisher), the publisher's own checksum where one exists,
our SHA-256 of every file, size and download time. Files are never modified afterwards; cleaning writes to
datasets/processed/ (see prepare.py). Nothing synthetic is downloaded or generated here.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ...config import DATASETS_DIR

RAW = DATASETS_DIR / "raw"
UA = {"User-Agent": "finora-dataset-acquisition/1.0 (academic project)"}

CKAN = "https://data.ok.gov/api/3/action/package_show?id="
OK_PACKAGES = ["state-of-oklahoma-purchase-card-pcard-fy-2021", "pcard-fy-2022", "purchase-card-pcard-fiscal-year-2023",
               "purchase-card-pcard-fiscal-year-2024"]

DATASETS = {
    "uci_credit": {
        "name": "Default of Credit Card Clients", "publisher": "UCI Machine Learning Repository (Yeh & Lien, 2009)",
        "page": "https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients", "doi": "10.24432/C55S3H",
        "licence": "CC BY 4.0", "real": "Real, anonymised customers of a Taiwanese bank (Apr-Sep 2005)",
        "files": [("default_of_credit_card_clients.zip", "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip", None)],
    },
    "oklahoma_pcard": {
        "name": "State of Oklahoma Purchase Card (PCard) transactions FY2021-FY2024",
        "publisher": "Oklahoma Office of Management and Enterprise Services (data.ok.gov)",
        "page": "https://data.ok.gov/dataset/purchase-card-pcard-fiscal-year-2024", "licence": "Creative Commons Attribution (CC BY)",
        "real": "Real purchase-card transactions of state agencies and higher-education institutions",
        "files": "ckan",
    },
    "dc_pcard": {
        "name": "District of Columbia Purchase Card Transactions", "publisher": "Government of the District of Columbia (Open Data DC)",
        "page": "https://opendata.dc.gov/datasets/purchase-card-transactions", "licence": "CC BY 4.0",
        "real": "Real purchase-card transactions of DC government agencies",
        "files": [("dc_purchase_card_transactions.csv",
                   "https://opendata.dc.gov/api/download/v1/items/92842dceac234b9ca1a8266fcfd57de7/csv?layers=50", None)],
    },
    "ulb_fraud": {
        "name": "Credit Card Fraud Detection (ULB Machine Learning Group / Worldline)", "publisher": "OpenML dataset 1597",
        "page": "https://www.openml.org/d/1597", "licence": "Public (OpenML licence field)",
        "citation": "Dal Pozzolo, Caelen, Johnson, Bontempi. Calibrating Probability with Undersampling for Unbalanced "
                    "Classification. IEEE CIDM 2015",
        "real": "Real card transactions of European cardholders, September 2013, with real fraud labels; features are PCA "
                "components except Time and Amount",
        # Official file: https://openml.org/data/v1/download/1673544/creditcard.arff (MD5 178bcf9bb1f31a3dfe12d0e577884add). That server
        # drops long downloads and ignores byte ranges, so the identical data is taken from Google's public mirror; its rows were checked
        # against the official ARFF (see datasets/raw/ulb_fraud/SOURCE.json and docs/PHASE_6_TRAINING.md).
        "files": [("creditcard.csv", "https://storage.googleapis.com/download.tensorflow.org/data/creditcard.csv", ("md5", "e90efcb83d69faf99fcab8b0255024de"))],
    },
    "moneyvis": {
        "name": "MoneyVis Bank Transactions Dataset", "publisher": "Robert S. Laramee, University of Nottingham (Mendeley Data)",
        "page": "https://data.mendeley.com/datasets/dnxtg6n4rv/1", "doi": "10.17632/dnxtg6n4rv.1", "licence": "CC BY 4.0",
        "citation": "Firat, Vytla, Singh, Jiang, Laramee. MoneyVis: Open Bank Transaction Data for Visualization and Beyond. "
                    "EuroVis 2023 short papers. doi:10.2312/evs.20231052",
        "real": "Real, anonymised transactions of ONE UK retail current account, about 7 years from July 2015",
        "files": [("laramee26openBankTransactionData.xlsx",
                   "https://data.mendeley.com/public-files/datasets/dnxtg6n4rv/files/36b3d359-2491-4282-850f-3f03e00fbfe3/file_downloaded",
                   ("sha256", "716eaf9ad4a3cf60dc9c9c8a20ed9a917c545a1b5f139f40ed91d2104faa3ff7"))],
    },
    "scf2022": {
        "name": "Survey of Consumer Finances 2022, summary extract", "publisher": "Board of Governors of the Federal Reserve System",
        "page": "https://www.federalreserve.gov/econres/scf_2022.htm", "licence": "US Federal Reserve public data (no restriction stated on the page; cite the Federal Reserve)",
        "real": "Real survey of 4,595 US families (22,975 records = 5 multiple-imputation implicates per family)",
        "files": [("scfp2022excel.zip", "https://www.federalreserve.gov/econres/files/scfp2022excel.zip", None),
                  ("codebk2022.txt", "https://www.federalreserve.gov/econres/files/codebk2022.txt", None)],
    },
}


def _get(url: str, dest: Path, tries: int = 4) -> None:
    """Download with the system curl: TLS is verified against the macOS keychain (the python.org build of Python has no
    CA bundle installed, and verification is never switched off)."""
    part = dest.with_suffix(dest.suffix + ".part")
    for i in range(tries):
        # -C - resumes a partial file (slow mirrors); the checksum check after download still guards integrity
        resume = ["-C", "-"] if part.exists() and part.stat().st_size > 0 else []
        r = subprocess.run(["curl", "-sSfL", *resume, "--retry", "2", "--max-time", "7200", "-A", UA["User-Agent"], "-o", str(part), url],
                           capture_output=True, text=True)
        if r.returncode == 33 and resume:          # server refuses byte ranges: start this file again from zero
            part.unlink()
        if r.returncode == 0:
            part.rename(dest)
            return
        if i == tries - 1:
            raise RuntimeError(f"download failed ({r.returncode}): {r.stderr.strip()[:300]}")
        print(f"    retry {i + 1}: {r.stderr.strip()[:120]}")
        time.sleep(2 ** (i + 1))


def _json(url: str) -> dict:
    r = subprocess.run(["curl", "-sSfL", "--max-time", "120", "-A", UA["User-Agent"], url], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _hash(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _ckan_files() -> list[tuple[str, str, None]]:
    out = []
    for pkg in OK_PACKAGES:
        res = _json(CKAN + pkg)["result"]
        lic = res.get("license_title")
        if not lic or "Creative Commons" not in lic:
            raise RuntimeError(f"{pkg}: licence is '{lic}', not Creative Commons - not approved for download")
        for x in res["resources"]:
            if x.get("url", "").lower().endswith(".csv"):
                name = f"{pkg}__{Path(x['url']).name}"
                if any(n == name for n, _, _ in out):
                    # the publisher served two DIFFERENT resources under one file name (FY2022: February and March 2022 are
                    # both 'pcard_public_202203.csv'); keep both, disambiguated by the resource id from the URL
                    name = f"{pkg}__{x['id'][:8]}__{Path(x['url']).name}"
                out.append((name, x["url"], None))
    return out


def acquire(key: str) -> dict:
    spec = DATASETS[key]
    folder = RAW / key
    folder.mkdir(parents=True, exist_ok=True)
    files = _ckan_files() if spec["files"] == "ckan" else spec["files"]
    record = {k: v for k, v in spec.items() if k != "files"}
    record["files"] = []
    for name, url, expected in files:
        dest = folder / name
        if not dest.exists():
            print(f"  downloading {key}/{name}")
            _get(url, dest)
        entry = {"file": name, "url": url, "bytes": dest.stat().st_size, "sha256": _hash(dest)}
        if expected:
            algo, value = expected
            got = _hash(dest, algo)
            if got != value:
                raise RuntimeError(f"{key}/{name}: publisher {algo} {value} does not match download {got}")
            entry[f"publisher_{algo}"] = value
            entry["publisher_checksum_verified"] = True
        record["files"].append(entry)
    record["downloaded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record["total_bytes"] = sum(f["bytes"] for f in record["files"])
    (folder / "SOURCE.json").write_text(json.dumps(record, indent=2))
    print(f"  {key}: {len(record['files'])} file(s), {record['total_bytes'] / 1e6:.1f} MB")
    return record


if __name__ == "__main__":
    for k in (sys.argv[1:] or list(DATASETS)):
        acquire(k)

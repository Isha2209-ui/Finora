"""Minimal, dependency-free reader for the first worksheet of an .xlsx file (an .xlsx is a zip of XML parts).
Values are returned exactly as stored: shared strings as text, numbers as text (callers convert)."""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_first_sheet(path: Path) -> list[list[str | None]]:
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheets = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
        root = ET.fromstring(z.read(sheets[0]))
    rows = []
    for r in root.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for c in r.findall("m:c", NS):
            v = c.find("m:v", NS)
            isel = c.find("m:is", NS)
            if c.get("t") == "s" and v is not None:
                val = shared[int(v.text)]
            elif c.get("t") == "inlineStr" and isel is not None:
                val = "".join(t.text or "" for t in isel.iter(f"{{{NS['m']}}}t"))
            else:
                val = v.text if v is not None else None
            cells[_col(c.get("r"))] = val
        if cells:
            rows.append([cells.get(i) for i in range(max(cells) + 1)])
    return rows

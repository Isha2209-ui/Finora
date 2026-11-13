"""PAN handling: validation, hashing and masking. Plain PANs are never stored or logged."""
import hashlib
import re

from ..config import PAN_PEPPER

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def normalise(pan: str) -> str:
    return (pan or "").strip().upper().replace(" ", "")


def is_valid(pan: str) -> bool:
    return bool(PAN_RE.match(normalise(pan)))


def validation_error(pan: str) -> str | None:
    p = normalise(pan)
    if not p:
        return "Please enter a PAN."
    if len(p) != 10:
        return "A PAN has exactly 10 characters (5 letters, 4 digits, 1 letter)."
    if not PAN_RE.match(p):
        return "Invalid PAN format. Expected 5 letters, 4 digits, then 1 letter (e.g. ABCDE1234F)."
    return None


def hash_pan(pan: str) -> str:
    return hashlib.sha256((PAN_PEPPER + normalise(pan)).encode()).hexdigest()


def mask(pan: str) -> str:
    p = normalise(pan)
    return p[:5] + "****" + p[-1]

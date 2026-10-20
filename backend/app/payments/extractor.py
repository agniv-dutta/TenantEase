"""Deterministic payment-message extractor (layer 1).

A pasted message is treated as data, never as instructions. This module pulls
out the amount, date, method, UPI/bank reference and a payer-name guess with
regular expressions, and can mask phone numbers and full UPI IDs before any
text is handed to an LLM. It never makes a decision about which lease a payment
belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app import clock

# ---------------------------------------------------------------------------
# Sensitive data masking
# ---------------------------------------------------------------------------

# Indian mobile numbers, with optional +91 / 0 prefix and spaces or dashes.
PHONE_RE = re.compile(r"(?:(?:\+|0{0,2})91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b")
# UPI handles look like something@okhdfcbank / name@paytm / 98xxxx@ybl.
UPI_ID_RE = re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b")
# 11-16 digit account / card numbers, optionally spaced in groups of four.
LONG_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){11,16}\d\b")


def mask_sensitive(text: str) -> str:
    """Replace phone numbers and UPI IDs with stable placeholders.

    Only the masked string may be sent to a provider; the original never
    leaves this process.
    """
    masked = PHONE_RE.sub("<phone>", text)
    masked = UPI_ID_RE.sub("<upi_id>", masked)
    masked = LONG_NUMBER_RE.sub("<account>", masked)
    return masked


# ---------------------------------------------------------------------------
# Method detection
# ---------------------------------------------------------------------------

# Order matters: the first match wins, so more specific apps come before "upi".
METHOD_KEYWORDS: list[tuple[str, str]] = [
    ("gpay", "upi"),
    ("google pay", "upi"),
    ("googlepay", "upi"),
    ("phonepe", "upi"),
    ("phone pe", "upi"),
    ("paytm", "upi"),
    ("bhim", "upi"),
    ("upi", "upi"),
    ("neft", "bank_transfer"),
    ("imps", "bank_transfer"),
    ("rtgs", "bank_transfer"),
    ("bank transfer", "bank_transfer"),
    ("net banking", "bank_transfer"),
    ("cheque", "cheque"),
    ("check", "cheque"),
    ("cash", "cash"),
    ("नकद", "cash"),
    ("कैश", "cash"),
    ("यूपीआई", "upi"),
]

CASH_HINTS = ("cash", "nakad", "नकद", "कैश", "हाथ", "हाथों")


# ---------------------------------------------------------------------------
# Amount detection
# ---------------------------------------------------------------------------

# "₹16,000", "Rs. 16000/-", "INR 16000", "16,000 rupees"
AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr|rupees?|रुपये|रु\.?)\s*([\d][\d,\s]*(?:\.\d{1,2})?)\s*(?:/-|/)?",
    re.IGNORECASE,
)
# A bare number that still looks like money: 4+ digits, optional Indian commas.
BARE_AMOUNT_RE = re.compile(r"\b(\d{1,2}(?:,\d{2}){1,3}|\d{4,7})\b")


def _to_int(value: str) -> int | None:
    """Parse a digit string with commas or spaces into an int."""
    cleaned = re.sub(r"[,\s]", "", value)
    if not cleaned or not cleaned.replace(".", "").isdigit():
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
# "16 Oct", "16 Oct 2026", "Oct 16", "16-10-2026", "16/10/26", "2026-10-16"
DATE_DMY_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
DATE_DMY_LONG_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_MONTH_NAME_RE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")[a-z]*\.?\s*(\d{4})?\b",
    re.IGNORECASE,
)
DATE_MONTH_FIRST_RE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2})(?:\s*,?\s*(\d{4}))?\b",
    re.IGNORECASE,
)


def _clamp_year(year: int) -> int:
    """Two-digit years map onto the demo decade."""
    if year < 100:
        return 2000 + year
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    """Build a date, returning None for impossible calendar days."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _find_date(text: str) -> date | None:
    """Pick the first plausible payment date in the message."""
    lowered = text.lower()

    match = DATE_ISO_RE.search(text)
    if match:
        found = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if found:
            return found

    match = DATE_DMY_LONG_RE.search(text)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if month > 12 and day <= 12:  # tolerate the occasional MM/DD
            day, month = month, day
        found = _safe_date(year, month, day)
        if found:
            return found

    match = DATE_MONTH_NAME_RE.search(lowered)
    if match:
        day = int(match.group(1))
        month = MONTHS[match.group(2)[:4]] if match.group(2)[:4] in MONTHS else MONTHS[match.group(2)[:3]]
        year = int(match.group(3)) if match.group(3) else clock.today().year
        found = _safe_date(_clamp_year(year), month, day)
        if found:
            return found

    match = DATE_MONTH_FIRST_RE.search(lowered)
    if match:
        month = MONTHS[match.group(1)[:4]] if match.group(1)[:4] in MONTHS else MONTHS[match.group(1)[:3]]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else clock.today().year
        found = _safe_date(_clamp_year(year), month, day)
        if found:
            return found

    match = DATE_DMY_RE.search(text)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if month > 12 and day <= 12:
            day, month = month, day
        found = _safe_date(_clamp_year(year), month, day)
        if found:
            return found

    if re.search(r"\b(aaj|today|abhi|just now|अभी|आज)\b", lowered):
        return clock.today()
    if re.search(r"\b(kal|yesterday|कल)\b", lowered):
        return clock.today() - timedelta(days=1)
    return None


# ---------------------------------------------------------------------------
# Reference detection
# ---------------------------------------------------------------------------

# UPI/bank reference numbers are alphanumeric ids of 6-22 chars, often labelled.
REF_LABELLED_RE = re.compile(
    r"(?:utr|ref(?:erence)?|txn|transaction|order|rrn|upi ref)[\s:#.-]*([A-Za-z0-9]{6,22})",
    re.IGNORECASE,
)
REF_BARE_RE = re.compile(r"\b([A-Z]{2,5}\d{6,16}|\d{10,16})\b")


def _find_reference(text: str) -> str | None:
    """Find a transaction reference, if the message carries one."""
    match = REF_LABELLED_RE.search(text)
    if match:
        return match.group(1)
    match = REF_BARE_RE.search(text)
    if match:
        return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Language + name guess
# ---------------------------------------------------------------------------

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
HINGLISH_HINTS = (
    "bhej", "bheja", "jama", "kiraya", "kar diya", "kar di", "hua", "aaya",
    "bhai", "kaun", "hai", "ho gaya", "paisa", "paise", "bhar diya", "de diya",
)
HINDI_PAY_HINTS = ("भेज", "जमा", "किराया", "दिया", "हो गया", "पैसा", "रुपये")


def guess_language(text: str) -> str:
    """Classify the message as en, hi or hinglish."""
    if DEVANAGARI_RE.search(text):
        return "hi"
    lowered = text.lower()
    if any(hint in lowered for hint in HINGLISH_HINTS):
        return "hinglish"
    return "en"


# Words that are never a payer name.
NAME_STOPWORDS = {
    "rent", "kiraya", "किराया", "upi", "gpay", "phonepe", "paytm", "neft", "imps",
    "payment", "paid", "sent", "received", "credited", "debited", "amount", "rs",
    "inr", "rupees", "bank", "sbi", "hdfc", "icici", "axis", "kotak", "a/c", "ac",
    "from", "to", "dear", "hello", "hi", "bhai", "ji", "ji,", "for", "se", "ke",
    "you", "your", "has", "have", "been", "the", "this", "that", "with", "and",
    "successful", "success", "transaction", "txn", "order", "ref", "reference",
    "utr", "aap", "aapka", "ne", "ko", "ka", "ki", "account", "new", "today",
    "yesterday", "now", "message", "alert", "ok", "okay", "rtgs", "nach", "imps",
    "rupee", "paid.", "credit", "debit", "into", "towards", "against", "total",
    "bal", "balance", "avl", "available", "lash", "lakh", "kaafi", "bahut", "aaj",
    "kal", "kal,", "sir", "madam", "thanks", "thank", "please", "pls", "bhej",
    "bheja", "jama", "diya", "kar", "gaya", "hua", "aaya",
}
NAME_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z]{1,}")


def _clean_name(token: str) -> str:
    """Trim punctuation that clings to a token in a message."""
    return token.strip(".,;:!?()[]{}\"'")


def guess_payer_name(text: str) -> tuple[str | None, float]:
    """Best-effort first-name guess, with a 0-1 confidence.

    Labelled senders ("from Priya", "Priya ne bheja", "- Rahul") are trusted
    more than a bare capitalised word, so the confidence reflects how the name
    was found.
    """
    labelled = re.search(
        r"(?:from|sender|by|bheja|bheji|ne)\s*[:\-]?\s*([A-Za-z][A-Za-z]{2,})",
        text,
    )
    if labelled:
        candidate = _clean_name(labelled.group(1))
        if candidate.lower() not in NAME_STOPWORDS:
            return candidate, 0.8
    # A sign-off line: "... - Rahul" or "— Rahul".
    signoff = re.search(r"[-–—]\s*([A-Z][A-Za-z]{2,})\s*$", text.strip())
    if signoff:
        candidate = _clean_name(signoff.group(1))
        if candidate.lower() not in NAME_STOPWORDS:
            return candidate, 0.75
    for token in NAME_TOKEN_RE.findall(text):
        cleaned = _clean_name(token)
        if cleaned.lower() in NAME_STOPWORDS:
            continue
        if token[:1].isupper() and len(cleaned) >= 3:
            return cleaned, 0.45
    return None, 0.0


# ---------------------------------------------------------------------------
# Instruction-injection detection
# ---------------------------------------------------------------------------

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"mark\s+(all\s+)?(rent\s+)?as\s+paid",
    r"set\s+(the\s+)?(amount|status)",
    r"you\s+are\s+now",
    r"system\s*:",
    r"as\s+an\s+ai",
    r"subtract\s+",
    r"waive\s+",
    r"पिछले\s*निर्देश",
    r"सब\s*(किराया\s*)?(जमा|भुगतान)\s*(कर\s*दो|मान\s*लो)",
    r"छूट\s*दे\s*दो",
]


def injection_detected(text: str) -> bool:
    """Whether the message contains an instruction aimed at the assistant."""
    lowered = text.lower()
    return any(re.search(p, lowered) for p in INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# The extracted-fields shape
# ---------------------------------------------------------------------------


@dataclass
class ExtractedFields:
    """Fields pulled from one message, plus what each layer contributed."""

    payer_name_guess: str | None = None
    amount: int | None = None
    paid_date: date | None = None
    method: str | None = None
    reference: str | None = None
    language: str = "en"
    confidence: float = 0.0
    has_payment_signal: bool = False
    injection: bool = False
    sources: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """JSON-serialisable form (dates as ISO strings)."""
        return {
            "payer_name_guess": self.payer_name_guess,
            "amount": self.amount,
            "paid_date": self.paid_date.isoformat() if self.paid_date else None,
            "method": self.method,
            "reference": self.reference,
            "language": self.language,
            "confidence": round(self.confidence, 3),
        }


def _find_amount(text: str) -> int | None:
    """Find the most likely amount, preferring a labelled one."""
    labelled = AMOUNT_RE.search(text)
    if labelled:
        value = _to_int(labelled.group(1))
        if value:
            return value
    for match in BARE_AMOUNT_RE.finditer(text):
        value = _to_int(match.group(1))
        # Ignore things that look like years or tiny numbers.
        if value and value >= 500 and not (1900 <= value <= 2100 and "," not in match.group(1)):
            return value
    return None


def _find_method(text: str) -> str | None:
    """Detect the payment method from app names and bank keywords."""
    lowered = text.lower()
    for keyword, method in METHOD_KEYWORDS:
        if keyword in lowered:
            return method
    return None


def extract_fields(text: str) -> ExtractedFields:
    """Run the deterministic layer over one message.

    ``has_payment_signal`` is true when the message actually looks like a
    payment (an amount or a payment verb). Messages with no payment at all are
    still parsed, but this flag lets the caller avoid raising false ones.
    """
    amount = _find_amount(text)
    method = _find_method(text)
    paid_date = _find_date(text)
    reference = _find_reference(text)
    name, name_conf = guess_payer_name(text)
    language = guess_language(text)
    injection = injection_detected(text)

    lowered = text.lower()
    verb_hits = any(hint in lowered for hint in HINGLISH_HINTS) or any(
        hint in text for hint in HINDI_PAY_HINTS
    )
    verb_hits = verb_hits or any(
        word in lowered
        for word in ("paid", "sent", "received", "credited", "transferred", "payment", "deposit")
    )
    has_signal = bool(amount or verb_hits)

    confidence_items = [name_conf]
    if amount:
        confidence_items.append(0.9)
    if paid_date:
        confidence_items.append(0.7)
    if method:
        confidence_items.append(0.6)
    confidence = sum(confidence_items) / len(confidence_items) if confidence_items else 0.0
    if injection:
        confidence *= 0.5

    return ExtractedFields(
        payer_name_guess=name,
        amount=amount,
        paid_date=paid_date,
        method=method,
        reference=reference,
        language=language,
        confidence=confidence,
        has_payment_signal=has_signal,
        injection=injection,
        sources={
            "payer_name_guess": "regex" if name else "none",
            "amount": "regex" if amount else "none",
            "paid_date": "regex" if paid_date else "none",
            "method": "regex" if method else "none",
            "reference": "regex" if reference else "none",
        },
    )

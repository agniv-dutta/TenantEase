"""Guardrails for drafted reminder messages.

Every check returns a pass/fail plus a human-readable reason that is shown to
the property manager in the drawer. On failure the drafter retries once with
the reasons appended, then falls back to a template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

BANNED_TERMS: dict[str, list[str]] = {
    "en": [
        "late fee", "late fees", "penalty", "penalties", "eviction", "evict",
        "legal action", "lawsuit", "court", "police", "deposit deduction",
        "credit score", "default notice", "terminate your lease",
    ],
    "hi": [
        "जुर्माना", "पेनल्टी", "कानूनी", "नोटिस", "पुलिस", "बेदखली",
        "खाली कराना", "क्रेडिट स्कोर", "मुकदमा", "अदालत",
    ],
    "hinglish": [
        "jurmana", "jurmna", "jurmnaa", "penalti", "kanooni", "kanoon",
        "bedakhli", "bedakhal", "police", "credit score", "mukadma",
        "adalat", "eviction", "evict", "late fee", "late fees", "legal action",
    ],
}


@dataclass
class CheckResult:
    """Outcome of a single guardrail."""

    name: str
    passed: bool
    reason: str

    def as_dict(self) -> dict:
        """JSON-serialisable form."""
        return {"name": self.name, "passed": self.passed, "reason": self.reason}


def check_valid_json(raw: str) -> CheckResult:
    """The provider must return valid JSON with a message string."""
    import json

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and isinstance(obj.get("message"), str):
            return CheckResult("valid_json", True, "Provider returned valid JSON.")
        return CheckResult("valid_json", False, "JSON must be an object with a string 'message' field.")
    except (json.JSONDecodeError, TypeError):
        return CheckResult("valid_json", False, "The reply was not valid JSON. Retry or use the template.")


def check_contains_amount(message: str, amount_str: str) -> CheckResult:
    """The message must contain the rent amount."""
    if amount_str in message:
        return CheckResult("contains_amount", True, "Includes the amount.")
    return CheckResult("contains_amount", False, f"The rent amount {amount_str} is missing.")


def check_contains_due_date(message: str, due_str: str) -> CheckResult:
    """The message must contain the due date."""
    if due_str in message or due_str.replace(" ", "") in message.replace(" ", ""):
        return CheckResult("contains_due_date", True, "Includes the due date.")
    return CheckResult("contains_due_date", False, f"The due date {due_str} is missing.")


def check_pay_link_once(message: str) -> CheckResult:
    """{PAY_LINK} must appear exactly once."""
    n = message.count("{PAY_LINK}")
    if n == 1:
        return CheckResult("pay_link_once", True, "Payment link appears exactly once.")
    if n == 0:
        return CheckResult("pay_link_once", False, "The payment link {PAY_LINK} is missing.")
    return CheckResult("pay_link_once", False, "The payment link {PAY_LINK} appears more than once.")


def check_length(message: str, limit: int = 280) -> CheckResult:
    """Messages must fit SMS/WhatsApp limits."""
    if len(message) <= limit:
        return CheckResult("length", True, f"Length {len(message)} is within {limit} characters.")
    return CheckResult("length", False, f"Length {len(message)} exceeds {limit} characters.")


def check_banned_terms(message: str, language: str) -> CheckResult:
    """No threats, fees or legal language in any of the three languages."""
    lowered = message.lower()
    hits: list[str] = []
    for lang_terms in (BANNED_TERMS["en"], BANNED_TERMS["hi"], BANNED_TERMS[language]):
        for term in lang_terms:
            if term.lower() in lowered and term not in hits:
                hits.append(term)
    if hits:
        return CheckResult(
            "banned_terms",
            False,
            "Contains banned wording: " + ", ".join(hits) + ". Remove it; the message must never threaten.",
        )
    return CheckResult("banned_terms", True, "No threats or late-fee language.")


def check_script_matches(message: str, language: str) -> CheckResult:
    """hi must use Devanagari; en and hinglish must not."""
    has_devanagari = bool(DEVANAGARI.search(message))
    if language == "hi" and not has_devanagari:
        return CheckResult("script", False, "Hindi must be written in Devanagari script.")
    if language in ("en", "hinglish") and has_devanagari:
        return CheckResult("script", False, "This language must be written in Latin script only.")
    return CheckResult("script", True, "Script matches the requested language.")


def check_digits(message: str, allowed: list[str]) -> CheckResult:
    """No digits other than the amount, due date and unit label."""
    remainder = message
    for token in allowed:
        if token:
            remainder = remainder.replace(token, "")
    stray = re.search(r"\d", remainder)
    if stray:
        return CheckResult(
            "digits",
            False,
            "Contains digits other than the amount and date. Remove them.",
        )
    return CheckResult("digits", True, "No stray digits beyond the amount and date.")


def check_all(
    message: str,
    language: str,
    amount_str: str,
    due_str: str,
    allowed_numeric_tokens: list[str] | None = None,
) -> list[CheckResult]:
    """Run every message guardrail and return all results."""
    allowed = allowed_numeric_tokens or []
    return [
        check_contains_amount(message, amount_str),
        check_contains_due_date(message, due_str),
        check_pay_link_once(message),
        check_length(message),
        check_banned_terms(message, language),
        check_script_matches(message, language),
        check_digits(message, [amount_str, due_str, *allowed]),
    ]


def all_passed(results: list[CheckResult]) -> bool:
    """True when every check passed."""
    return all(r.passed for r in results)


def failure_reasons(results: list[CheckResult]) -> list[str]:
    """Human-readable reasons for the failures, for the retry prompt."""
    return [r.reason for r in results if not r.passed]

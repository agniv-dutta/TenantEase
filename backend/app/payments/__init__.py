"""Payment parsing package.

Turns a pasted WhatsApp, UPI or bank SMS message into structured fields and a
short list of candidate leases. Nothing here posts a payment: it only proposes,
and a person confirms.
"""

from __future__ import annotations

from app.payments.extractor import ExtractedFields, extract_fields, mask_sensitive
from app.payments.matcher import LeaseMatch, match_leases
from app.payments.parser import ParseResult, parse_payment_message

__all__ = [
    "ExtractedFields",
    "LeaseMatch",
    "ParseResult",
    "extract_fields",
    "mask_sensitive",
    "match_leases",
    "parse_payment_message",
]

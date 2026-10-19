"""Maintenance request triage.

Classifies a free-text complaint (English, Hindi or Hinglish) into a small
structured shape:

    {category, urgency, suggested_trade, one_line_summary}

The preferred path asks the configured LLM for JSON and validates the reply
with Pydantic. With no provider (the default) or when validation fails, a
keyword classifier is used instead. Either way a hard safety rule runs last:
anything that mentions a gas smell, sparks, fire, flooding or a structural
crack is forced to ``emergency`` regardless of what the model said.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ValidationError

from app.llm import provider as provider_mod


class Category(str, Enum):
    """Maintenance category."""

    plumbing = "plumbing"
    gas = "gas"
    electrical = "electrical"
    appliance = "appliance"
    structural = "structural"
    pest = "pest"
    other = "other"


class Urgency(str, Enum):
    """How soon the request needs attention."""

    emergency = "emergency"
    soon = "soon"
    routine = "routine"


class Triage(BaseModel):
    """Structured triage output."""

    category: Category
    urgency: Urgency
    suggested_trade: str
    one_line_summary: str


TRIAGE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "category": {"enum": [c.value for c in Category]},
        "urgency": {"enum": [u.value for u in Urgency]},
        "suggested_trade": {"type": "string"},
        "one_line_summary": {"type": "string"},
    },
    "required": ["category", "urgency", "suggested_trade", "one_line_summary"],
    "additionalProperties": False,
}

TRADE_BY_CATEGORY: dict[Category, str] = {
    Category.plumbing: "plumber",
    Category.gas: "gas technician",
    Category.electrical: "electrician",
    Category.appliance: "appliance technician",
    Category.structural: "mason",
    Category.pest: "pest control",
    Category.other: "general handyman",
}

# Safety phrases. A match here forces an emergency, whatever the model said.
EMERGENCY_PATTERNS: dict[str, list[str]] = {
    "gas smell": [
        r"gas\s*(leak|smell|leaking)",
        r"smell\s*of\s*gas",
        r"gas\s*ki\s*(smell|gandh|boo)",
        r"gas\s*nikal",
        r"गैस.*(गंध|रिस|स्मेल|लिक)",
    ],
    "sparks": [r"spark", r"chingari", r"चिंगारी", r"स्पार्क"],
    "fire": [r"\bfire\b", r"\baag\b", r"आग", r"जल(ा|ने)\s*रहा"],
    "flooding": [
        r"flood",
        r"paani\s*bhar",
        r"पानी\s*भर",
        r"water\s*(everywhere|coming\s*in|gushing|overflow)",
        r"overflow(ing)?\s*(water|sewer|toilet)?",
        r"gushing",
    ],
    "structural cracks": [
        r"(wall|ceiling|roof|beam|pillar|slab|column|foundation|structural)\s*(crack|darar)",
        r"crack\s*(in|on)\s*(the\s*)?(wall|ceiling|roof|beam|pillar|slab|column|foundation)",
        r"structural\s*crack",
        r"\bdarar\b",
        r"दरार",
        r"दीवार.*(दरार|चटक)",
    ],
}

CATEGORY_KEYWORDS: dict[Category, list[str]] = {
    Category.plumbing: [
        "pipe", "tap", "faucet", "nal", "toilet", "flush", "commode", "drain",
        "sink", "basin", "bathroom", "sewage", "sewer", "water supply", "tank",
        "tanki", "borewell", "paani", "पाइप", "नल", "शौचालय", "टंकी",
        "सीवेज", "पानी", "रिस",
    ],
    Category.gas: [
        "gas", "gas stove", "gas line", "gas cylinder", "gas meter", "gas burner",
        "gas chulha", "गैस",
    ],
    Category.electrical: [
        "light", "bulb", "switch", "socket", "wiring", "wire", "fan", "power",
        "current", "mcb", "fuse", "meter", "electricity", "short circuit",
        "shock", "लाइट", "बिजली", "करंट", "स्विच", "पंखा",
    ],
    Category.appliance: [
        "refrigerator", "fridge", "air conditioner", " ac ", " ac,", " ac.",
        "washing machine", "microwave", "geyser", "chimney", "television",
        " tv ", "not cooling", "remote", "फ्रिज", "गीज़र", "वाशिंग मशीन",
        "एसी",
    ],
    Category.structural: [
        "wall", "ceiling", "roof", "chhat", "seepage", "damp", "plaster",
        "paint", "floor", "tile", "deewar", "दीवार", "छत", "सीलन", "प्लास्टर",
    ],
    Category.pest: [
        "cockroach", "rat", "mouse", "mosquito", "termite", "bug", "insect",
        "ant", "pest", "deemak", "machhar", "कॉकरोच", "चूहा", "मच्छर", "दीमक",
        "कीड़े",
    ],
    Category.other: ["parking", "intercom", "lift", "elevator", "main door", "lock"],
}

SOON_TERMS = [
    "urgent", "asap", "immediately", "right now", "today", "turant", "तुरंत",
    "no water", "no electricity", "no power", "choked", "blocked", "band padi",
    "band hai", "unusable", "not working", "जल्दी", "बंद पड़ी", "बंद है",
    "पानी नहीं",
]


@dataclass
class TriageResult:
    """The outcome of one triage attempt."""

    triage: Triage
    method: str  # llm | keyword
    forced_emergency: bool = False
    notes: list[str] = field(default_factory=list)


def emergency_reasons(text: str) -> list[str]:
    """Return the safety reasons a complaint is an emergency, if any."""
    lowered = text.lower()
    hits: list[str] = []
    for reason, patterns in EMERGENCY_PATTERNS.items():
        if any(re.search(p, lowered) for p in patterns):
            hits.append(reason)
    return hits


def keyword_classify(text: str) -> Triage:
    """Deterministic keyword classifier used as the fallback."""
    lowered = f" {text.lower()} "
    scores: dict[Category, int] = {}
    for category, words in CATEGORY_KEYWORDS.items():
        score = sum(1 for w in words if w in lowered)
        if score:
            scores[category] = score
    category = max(scores, key=lambda c: scores[c]) if scores else Category.other
    urgency = Urgency.soon if any(t in lowered for t in SOON_TERMS) else Urgency.routine
    summary = _summarise(category, text)
    return Triage(
        category=category,
        urgency=urgency,
        suggested_trade=TRADE_BY_CATEGORY[category],
        one_line_summary=summary,
    )


def _summarise(category: Category, text: str) -> str:
    """A short English summary for the manager."""
    clean = " ".join(text.split())
    if len(clean) > 90:
        clean = clean[:87].rstrip() + "..."
    return f"{category.value.capitalize()} issue: {clean}"


SYSTEM_PROMPT = (
    "You triage maintenance complaints for a small residential landlord in India. "
    "You will be given one complaint in English, Hindi or Hinglish. Reply with a "
    "single JSON object and nothing else, matching this schema:\n"
    + json.dumps(TRIAGE_JSON_SCHEMA, ensure_ascii=False)
    + "\nRules: choose category from the enum; choose urgency emergency only for a "
    "threat to safety (gas smell, sparks, fire, flooding, structural cracks), soon "
    "when the unit is hard to live in, otherwise routine. suggested_trade is a short "
    "trade name in English. one_line_summary is one short English sentence. Never "
    "invent names, phone numbers or addresses. If unsure, use category 'other'."
)


def _llm_classify(text: str) -> Triage:
    """Ask the provider for JSON and validate it with Pydantic."""
    raw = provider_mod.complete(SYSTEM_PROMPT, text, max_tokens=256)
    data = json.loads(raw)
    return Triage.model_validate(data)


def classify(text: str) -> TriageResult:
    """Classify a complaint, then apply the emergency safety override.

    Tries the provider first when one is configured; falls back to the keyword
    classifier on any error or validation failure. The safety override always
    runs last.
    """
    notes: list[str] = []
    method = "keyword"
    if provider_mod.provider_available():
        try:
            triage = _llm_classify(text)
            method = "llm"
        except (provider_mod.ProviderError, json.JSONDecodeError, ValidationError, TypeError, KeyError) as exc:
            notes.append(f"LLM triage unavailable ({type(exc).__name__}); used the keyword classifier.")
            triage = keyword_classify(text)
    else:
        triage = keyword_classify(text)
        notes.append("No LLM provider configured, so the keyword classifier was used.")

    reasons = emergency_reasons(text)
    forced = False
    if reasons and triage.urgency is not Urgency.emergency:
        triage = triage.model_copy(update={"urgency": Urgency.emergency})
        forced = True
    if reasons:
        notes.append("Safety rule forced an emergency: " + ", ".join(reasons) + ".")
    return TriageResult(triage=triage, method=method, forced_emergency=forced, notes=notes)

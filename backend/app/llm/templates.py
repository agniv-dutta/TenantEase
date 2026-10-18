"""Fallback message templates: 3 languages x 3 tones.

* ``en`` — English in Latin script
* ``hi`` — Hindi in Devanagari
* ``hinglish`` — Hindi in Roman script, the way people text

Templates always pass the guardrails, so they are safe fallbacks when the LLM
provider is absent or its output fails validation. No banned terms appear in
any template.
"""

from __future__ import annotations

TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "friendly": (
            "Hi {name}, just a friendly reminder that rent of Rs {amount} is due "
            "on {due}. You can pay here: {PAY_LINK}. Thank you!"
        ),
        "neutral": (
            "Reminder: rent of Rs {amount} is due on {due}. Payment link: "
            "{PAY_LINK}. Please arrange payment by the due date."
        ),
        "polite_firm": (
            "Requesting you to clear the pending rent of Rs {amount} due on {due} "
            "at the earliest. Payment link: {PAY_LINK}. Thank you."
        ),
    },
    "hi": {
        "friendly": (
            "नमस्ते {name}, {due} को {amount} रुपये का किराया देय है। "
            "यहाँ भुगतान करें: {PAY_LINK}। धन्यवाद।"
        ),
        "neutral": (
            "सूचना: {due} को {amount} रुपये का किराया देय है। "
            "भुगतान लिंक: {PAY_LINK}। कृपया समय पर भुगतान करें।"
        ),
        "polite_firm": (
            "कृपया {due} को देय {amount} रुपये का किराया शीघ्र जमा करें। "
            "भुगतान लिंक: {PAY_LINK}। धन्यवाद।"
        ),
    },
    "hinglish": {
        "friendly": (
            "Namaste {name}, {due} ko {amount} rupaye ka kiraya due hai. "
            "Yahan pay karein: {PAY_LINK}. Dhanyavaad."
        ),
        "neutral": (
            "Reminder: {due} ko {amount} rupaye ka kiraya due hai. Payment link: "
            "{PAY_LINK}. Kripya samay par bhugtan karein."
        ),
        "polite_firm": (
            "Kripya {due} ko due {amount} rupaye ka kiraya jald se jald jama "
            "karein. Payment link: {PAY_LINK}. Dhanyavaad."
        ),
    },
}


def render_template(language: str, tone: str, name: str, amount: str, due: str) -> str:
    """Render a fallback template with the minimised facts."""
    template = TEMPLATES[language][tone]
    return template.format(name=name, amount=amount, due=due, PAY_LINK="{PAY_LINK}")

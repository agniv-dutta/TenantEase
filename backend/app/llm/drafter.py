"""Draft orchestration: provider -> parse -> guardrails -> retry -> fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.llm import prompts
from app.llm import provider as provider_mod
from app.llm.guardrails import CheckResult, all_passed, check_all, check_valid_json, failure_reasons
from app.llm.templates import render_template


@dataclass
class DraftResult:
    """The outcome of one drafting attempt."""

    message: str
    source: str  # llm | template | fallback
    guardrails: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def draft_message(
    first_name: str,
    unit_label: str,
    amount_inr: int,
    due_str: str,
    language: str,
    tone: str,
    acknowledge_overdue: bool,
    allowed_numeric_tokens: list[str] | None = None,
) -> DraftResult:
    """Draft a reminder message, guarding every attempt.

    The LLM sees only the minimised facts in ``prompts.user_prompt``. On
    provider absence the template is used directly (source ``template``); on
    two failed attempts or a provider error the template is used as a
    recorded fallback (source ``fallback``).
    """
    amount_str = f"{amount_inr:,}"
    template_msg = render_template(
        language, tone, first_name.split()[0], amount_str, due_str
    )
    template_check = check_all(template_msg, language, amount_str, due_str, allowed_numeric_tokens)

    if not provider_mod.provider_available():
        return DraftResult(
            message=template_msg,
            source="template",
            guardrails=[r.as_dict() for r in template_check],
            notes=["No LLM provider configured, so the vetted template was used."],
        )

    system = prompts.SYSTEM_PROMPT
    user = prompts.user_prompt(
        first_name.split()[0], unit_label, amount_inr, due_str, language, tone, acknowledge_overdue
    )
    attempts: list[str] = []
    try:
        raw = provider_mod.complete(system, user)
        message, results, notes = _validate(raw, language, amount_str, due_str, allowed_numeric_tokens)
        if results is not None and all_passed(results):
            return DraftResult(message, "llm", [r.as_dict() for r in results], notes)
        attempts = failure_reasons(results) if results is not None else ["Reply was not valid JSON."]
        # Retry once with the violation reasons appended.
        retry_user = user + "\n\nFix these violations:\n" + "\n".join(f"- {r}" for r in attempts)
        raw2 = provider_mod.complete(system, retry_user)
        message2, results2, notes2 = _validate(
            raw2, language, amount_str, due_str, allowed_numeric_tokens
        )
        if results2 is not None and all_passed(results2):
            return DraftResult(message2, "llm", [r.as_dict() for r in results2], notes2)
        notes_fall = notes2 + ["The model failed guardrails twice, so the vetted template was used."]
        return DraftResult(
            template_msg,
            "fallback",
            [r.as_dict() for r in template_check],
            notes_fall,
        )
    except provider_mod.ProviderError as exc:
        return DraftResult(
            template_msg,
            "fallback",
            [r.as_dict() for r in template_check],
            [f"LLM provider error: {exc}. The vetted template was used instead."],
        )


def _validate(
    raw: str,
    language: str,
    amount_str: str,
    due_str: str,
    allowed_numeric_tokens: list[str] | None,
) -> tuple[str, list[CheckResult] | None, list[str]]:
    """Validate a provider reply; returns (message, checks, notes)."""
    json_check = check_valid_json(raw)
    if not json_check.passed:
        return "", [json_check], []
    try:
        message = json.loads(raw)["message"]
    except (json.JSONDecodeError, TypeError, KeyError):
        return "", [json_check], []
    checks = [json_check] + check_all(
        message, language, amount_str, due_str, allowed_numeric_tokens
    )
    return message, checks, []

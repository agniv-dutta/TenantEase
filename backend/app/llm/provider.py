"""Provider interface for LLM completion.

Providers: ``anthropic``, ``openai``, ``ollama``, ``none``. With ``none``
(the default) no network call is made and drafting falls back to templates.
"""

from __future__ import annotations

import json
import os


class ProviderError(RuntimeError):
    """Raised when a provider fails; callers fall back to templates."""


def complete(system: str, user: str, max_tokens: int = 512) -> str:
    """Return the assistant completion for a system/user prompt pair."""
    provider = os.environ.get("LLM_PROVIDER", "none").lower()
    model = os.environ.get("LLM_MODEL", "claude-3-5-haiku-latest")
    if provider == "none":
        raise ProviderError("LLM_PROVIDER is none")
    if provider == "anthropic":
        return _anthropic_complete(system, user, model, max_tokens)
    if provider == "openai":
        return _openai_complete(system, user, model, max_tokens)
    if provider == "ollama":
        return _ollama_complete(system, user, model, max_tokens)
    raise ProviderError(f"Unknown LLM_PROVIDER: {provider}")


def _anthropic_complete(system: str, user: str, model: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise ProviderError("anthropic SDK not installed") from exc
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
    )
    return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")


def _openai_complete(system: str, user: str, model: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise ProviderError("openai SDK not installed") from exc
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content or ""


def _ollama_complete(system: str, user: str, model: str, max_tokens: int) -> str:
    import httpx

    r = httpx.post(
        "http://localhost:11434/api/chat",
        json={
            "model": model,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise ProviderError(f"ollama returned {r.status_code}")
    return json.loads(r.text)["message"]["content"]


def provider_available() -> bool:
    """Whether a real provider is configured."""
    return os.environ.get("LLM_PROVIDER", "none").lower() != "none"

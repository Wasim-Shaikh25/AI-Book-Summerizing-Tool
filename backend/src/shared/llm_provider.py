"""Single source of truth for LLM chat provider selection (OpenAI | OpenRouter)."""

from __future__ import annotations

from src import config

_PROVIDER_ALIASES = {
    "CHATGPT": "OPENAI",
}

_LLM_PROVIDER_TO_BACKEND = {
    "OPENAI": "openai",
    "OPENROUTER": "openrouter",
}

_CHAT_PROVIDER_ALIASES = {
    "chatgpt": "openai",
}

CLOUD_CHAT_PROVIDERS = frozenset({"openai", "openrouter"})
ALL_CHAT_PROVIDERS = frozenset({"openai", "openrouter"})


def normalize_chat_provider(raw: str) -> str:
    p = (raw or "").strip().lower()
    return _CHAT_PROVIDER_ALIASES.get(p, p)


def backend_from_llm_provider(raw: str = "") -> str:
    """Map config ``LLM_PROVIDER`` enum to runtime backend slug."""
    p = (raw or config.LLM_PROVIDER or "OPENAI").strip().upper()
    p = _PROVIDER_ALIASES.get(p, p)
    return _LLM_PROVIDER_TO_BACKEND.get(p, "openai")


def active_chat_provider() -> str:
    """Primary chat backend for the whole application."""
    return backend_from_llm_provider(config.LLM_PROVIDER)


def resolve_stage_provider(override: str = "") -> str:
    """Provider for a pipeline stage — override if set, else ``LLM_PROVIDER``."""
    if (override or "").strip():
        return normalize_chat_provider(override)
    return active_chat_provider()


def rewrite_provider_order() -> list[str]:
    """Ordered rewrite backends — defaults to a single entry from ``LLM_PROVIDER``."""
    raw = (config.REWRITE_PROVIDER_ORDER or "").strip()
    if raw:
        return [normalize_chat_provider(p) for p in raw.split(",") if p.strip()]
    return [active_chat_provider()]


def is_cloud_chat_provider(provider: str) -> bool:
    return normalize_chat_provider(provider) in CLOUD_CHAT_PROVIDERS


def is_chat_provider(provider: str) -> bool:
    return normalize_chat_provider(provider) in ALL_CHAT_PROVIDERS


def intent_refiner_backend() -> str:
    """Backend for prompt refinement — follows ``LLM_PROVIDER`` unless overridden."""
    import os

    raw = os.environ.get("INTENT_REFINER_BACKEND", "").strip().lower()
    if raw:
        return raw
    provider = active_chat_provider()
    if provider in CLOUD_CHAT_PROVIDERS:
        return provider
    return "passthrough"

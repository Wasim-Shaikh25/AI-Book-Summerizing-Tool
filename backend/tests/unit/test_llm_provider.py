"""Tests for centralized LLM provider resolution."""

from __future__ import annotations

from src.shared import llm_provider


def test_active_chat_provider_openrouter(monkeypatch) -> None:
    monkeypatch.setattr(llm_provider.config, "LLM_PROVIDER", "OPENROUTER")
    assert llm_provider.active_chat_provider() == "openrouter"


def test_rewrite_provider_order_single_provider(monkeypatch) -> None:
    monkeypatch.setattr(llm_provider.config, "LLM_PROVIDER", "OPENROUTER")
    monkeypatch.setattr(llm_provider.config, "REWRITE_PROVIDER_ORDER", "")
    assert llm_provider.rewrite_provider_order() == ["openrouter"]


def test_rewrite_provider_order_no_openai_fallback_when_openrouter(monkeypatch) -> None:
    monkeypatch.setattr(llm_provider.config, "LLM_PROVIDER", "OPENROUTER")
    monkeypatch.setattr(llm_provider.config, "REWRITE_PROVIDER_ORDER", "openrouter")
    order = llm_provider.rewrite_provider_order()
    assert order == ["openrouter"]
    assert "openai" not in order


def test_resolve_stage_provider_uses_override(monkeypatch) -> None:
    monkeypatch.setattr(llm_provider.config, "LLM_PROVIDER", "OPENAI")
    assert llm_provider.resolve_stage_provider("openrouter") == "openrouter"


def test_intent_refiner_backend_follows_llm_provider(monkeypatch) -> None:
    monkeypatch.setattr(llm_provider.config, "LLM_PROVIDER", "OPENROUTER")
    monkeypatch.delenv("INTENT_REFINER_BACKEND", raising=False)
    assert llm_provider.intent_refiner_backend() == "openrouter"

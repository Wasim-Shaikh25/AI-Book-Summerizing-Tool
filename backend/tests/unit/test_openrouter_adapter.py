"""Tests for OpenRouter chat adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.modules.pipeline.openrouter_adapter import chat_openrouter


def test_chat_openrouter_returns_content(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    payload = {
        "choices": [{"message": {"content": "Hello from free model"}}],
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        text, model = chat_openrouter(system="sys", user="hi", max_tokens=50)

    assert text == "Hello from free model"
    assert model == "openrouter/free"


def test_chat_openrouter_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("src.modules.pipeline.openrouter_adapter.openrouter_api_key", lambda: "")
    text, model = chat_openrouter(system="sys", user="hi", max_tokens=50)
    assert text is None
    assert model == ""

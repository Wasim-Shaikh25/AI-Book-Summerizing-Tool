"""Tests for LlmChatClient OpenRouter routing."""

from __future__ import annotations

from unittest.mock import patch

from src.modules.pipeline.llm_chat_client import LlmChatClient


def test_chat_with_provider_openrouter() -> None:
    client = LlmChatClient("openrouter")
    with patch.object(client, "_chat_openrouter", return_value="ok") as mock_fn:
        out = client.chat_with_provider("openrouter", system="s", user="u", max_tokens=10)
    assert out == "ok"
    mock_fn.assert_called_once()

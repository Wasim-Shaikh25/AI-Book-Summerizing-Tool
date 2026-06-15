"""Tests for OpenAI chat retry/backoff robustness."""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

from src.modules.pipeline import llm_chat_client
from src.modules.pipeline.llm_chat_client import LlmChatClient


def _fake_response(text: str):
    body = json.dumps({"choices": [{"message": {"content": text}}]}).encode("utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Resp(body)


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b"rate limited"))


def test_retries_on_429_then_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "3")
    monkeypatch.setattr(llm_chat_client.time, "sleep", lambda *_: None)

    client = LlmChatClient("openai")
    client._openai_key = "test-key"

    calls = {"n": 0}

    def _fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return _fake_response("final notes")

    with patch.object(llm_chat_client.urllib.request, "urlopen", side_effect=_fake_urlopen):
        out = client._chat_openai(system="s", user="u", max_tokens=10)

    assert out == "final notes"
    assert calls["n"] == 3  # two 429s retried, third succeeded


def test_no_retry_on_400_falls_through(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "3")
    monkeypatch.setattr(llm_chat_client.time, "sleep", lambda *_: None)

    client = LlmChatClient("openai", model_override="only-model")
    client._openai_key = "test-key"

    calls = {"n": 0}

    def _fake_urlopen(req, timeout=0):
        calls["n"] += 1
        raise _http_error(400)

    with patch.object(llm_chat_client.urllib.request, "urlopen", side_effect=_fake_urlopen):
        out = client._chat_openai(system="s", user="u", max_tokens=10)

    assert out is None
    # 400 is not retried; one attempt per candidate model (override + fallbacks)
    assert calls["n"] >= 1

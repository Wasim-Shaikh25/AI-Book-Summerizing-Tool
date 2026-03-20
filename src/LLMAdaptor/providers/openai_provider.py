from __future__ import annotations

from typing import Optional

import requests

# Avoid importing OPENAI_* constants at module import time because tests may
# monkeypatch env vars and reload src.config.

from .base import LLMResult


class OpenAIProvider:
    """
    OpenAI provider (Chat Completions API).

    Environment/config:
      - OPENAI_API_KEY (required)
      - OPENAI_MODEL (default: gpt-4o-mini)
      - OPENAI_BASE_URL (default: https://api.openai.com)

    Notes:
      - response_mime_type containing "json" will request JSON mode via response_format
        when supported by the selected model.
    """

    name = "OPENAI"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 600.0,
    ):
        from src import config as cfg

        self.api_key = (api_key or getattr(cfg, "OPENAI_API_KEY", "") or "").strip()
        self.base_url = (base_url or getattr(cfg, "OPENAI_BASE_URL", "") or "https://api.openai.com").rstrip("/")
        self.model = (model or getattr(cfg, "OPENAI_MODEL", "") or "gpt-4o-mini").strip()
        self.timeout_s = float(timeout_s)

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Set env var OPENAI_API_KEY (or add it to .env) to use ACTIVE_MODEL=OPENAI."
            )

    def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
    ) -> LLMResult:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user or ""},
            ],
            "temperature": float(temperature),
        }

        # max_tokens is supported by Chat Completions (some newer models prefer max_output_tokens,
        # but max_tokens still works for many; keep it for compatibility).
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        # NOTE:
        # Do NOT force OpenAI JSON mode here. OpenAI's json_object mode requires a top-level object,
        # but many of our prompts (e.g. toc_classifier) require a top-level JSON array.
        # We rely on prompt instructions + downstream tolerant parsing instead.

        r = requests.post(url, headers=headers, json=payload, timeout=(10.0, self.timeout_s))
        r.raise_for_status()
        data = r.json()

        text = ""
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = ""

        usage = data.get("usage")
        return LLMResult(text=text or "", raw=data, usage=usage)

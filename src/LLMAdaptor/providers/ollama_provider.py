from __future__ import annotations

import json
from typing import Optional

import requests

from src.config import BASE_DIR

from .base import LLMResult


class QwenProvider:
    """
    Local Qwen provider via Ollama.

    Requires:
      - Ollama running at http://localhost:11434
      - A Qwen model pulled, e.g. `ollama pull qwen2.5:7b`

    Uses Ollama's /api/chat endpoint.
    """

    name = "QWEN"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        timeout_s: float = 180.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
    ) -> LLMResult:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": float(temperature),
            },
        }

        # Ollama's max tokens option is `num_predict`
        if max_tokens is not None:
            payload["options"]["num_predict"] = int(max_tokens)

        # If caller expects JSON, we can bias with format=json (Ollama supports this)
        if response_mime_type and "json" in response_mime_type.lower():
            payload["format"] = "json"

        r = requests.post(url, json=payload, timeout=self.timeout_s)
        r.raise_for_status()

        data = r.json()
        msg = (data.get("message") or {}).get("content")
        if not isinstance(msg, str):
            msg = ""

        return LLMResult(text=msg, raw=data, usage=data.get("eval_count"))

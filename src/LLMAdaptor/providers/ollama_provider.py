from __future__ import annotations

import json
from typing import Optional

import requests

from src.config import BASE_DIR

from .base import LLMResult


class OllamaProvider:
    """
    Local Ollama provider.

    This provider can run any Ollama model (Qwen, Gemma, etc.).

    Requires:
      - Ollama running at http://localhost:11434
      - A Qwen model pulled, e.g. `ollama pull qwen2.5:7b`

    Uses Ollama's /api/chat endpoint.
    """

    name = "OLLAMA"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "gemma3:270m",
        timeout_s: float = 600.0,
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
        """
        Ollama 0.18.0 doesn't expose /api/chat; use /api/generate instead.

        We still accept (system, user) and combine them into a single prompt.
        """
        url = f"{self.base_url}/api/generate"
        prompt = f"{system}\n\n{user}"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
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

        # Requests timeout expects seconds or (connect, read). Use (connect, read) so
        # we don't fail on long generations.
        r = requests.post(url, json=payload, timeout=(10.0, self.timeout_s))
        r.raise_for_status()

        data = r.json()
        msg = data.get("response")
        if not isinstance(msg, str):
            msg = ""

        return LLMResult(text=msg, raw=data, usage=data.get("eval_count"))

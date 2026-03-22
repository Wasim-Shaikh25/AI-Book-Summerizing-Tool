from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from google import genai

from .base import LLMResult


@dataclass(frozen=True, slots=True)
class _GeminiResponse:
    raw_text: str
    parsed_json: Optional[Any]
    model: Optional[str]


def _gemini_generate(
    system_instruction: str,
    user_prompt: str,
    *,
    model: str = "gemini-1.5-flash",
    temperature: float = 0.0,
) -> _GeminiResponse:
    from src import config as cfg

    api_key = (getattr(cfg, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set (env or .env).")

    model = (getattr(cfg, "GEMINI_MODEL", "") or model).strip()
    if model.startswith("models/"):
        model = model[len("models/") :]

    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_instruction,
            "temperature": float(temperature),
        },
    )

    raw = (getattr(resp, "text", "") or "").strip()

    parsed: Optional[Any] = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    return _GeminiResponse(raw_text=raw, parsed_json=parsed, model=model)


class GeminiProvider:
    name = "GEMINI"

    def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
    ) -> LLMResult:
        # NOTE:
        # - max_tokens/response_mime_type are currently ignored because google.genai surface differs per model.
        # - Keep signature aligned with other providers; we can map these later.
        t0 = time.perf_counter()
        resp = _gemini_generate(system, user, temperature=temperature)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        return LLMResult(
            text=resp.raw_text,
            raw={"parsed_json": resp.parsed_json},
            usage=None,
            model=resp.model or self.name,
            latency_ms=latency_ms,
        )

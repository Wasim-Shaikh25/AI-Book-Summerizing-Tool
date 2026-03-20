from __future__ import annotations

from typing import Optional

import time

from src.ai.gemini_adapter import gemini_generate

from .base import LLMResult


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
        # Current gemini_generate signature supports only (system_instruction, user_prompt, model=...).
        # Temperature/max_tokens/response_mime_type are ignored here for now to maintain compatibility.
        t0 = time.perf_counter()
        resp = gemini_generate(system, user)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Best-effort model name capture (depends on adapter response shape)
        model_name = None
        try:
            model_name = getattr(resp, "model", None) or getattr(resp, "model_name", None)
        except Exception:
            model_name = None

        return LLMResult(
            text=resp.raw_text,
            raw={"parsed_json": resp.parsed_json},
            usage=None,
            model=model_name or self.name,
            latency_ms=latency_ms,
        )

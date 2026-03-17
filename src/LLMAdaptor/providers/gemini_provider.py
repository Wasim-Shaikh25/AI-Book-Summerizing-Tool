from __future__ import annotations

from typing import Optional

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
        resp = gemini_generate(system, user)
        return LLMResult(text=resp.raw_text, raw={"parsed_json": resp.parsed_json}, usage=None)

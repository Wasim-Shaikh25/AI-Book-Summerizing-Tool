from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import google.generativeai as genai


@dataclass(frozen=True, slots=True)
class GeminiResponse:
    """
    Simple wrapper around the model output for logging/debugging.
    """
    raw_text: str
    parsed_json: Optional[Any]


def gemini_generate(system_instruction: str, user_prompt: str, *, model: str = "models/gemini-flash-latest") -> GeminiResponse:
    """
    Minimal Gemini adapter used by the clean pipeline.

    Env:
      - GEMINI_API_KEY must be set.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)

    m = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_instruction,
    )

    resp = m.generate_content(user_prompt)
    raw = (resp.text or "").strip()

    parsed: Optional[Any] = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    return GeminiResponse(raw_text=raw, parsed_json=parsed)

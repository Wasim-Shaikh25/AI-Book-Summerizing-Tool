from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from google import genai


@dataclass(frozen=True, slots=True)
class GeminiResponse:
    """
    Simple wrapper around the model output for logging/debugging.
    """
    raw_text: str
    parsed_json: Optional[Any]


def gemini_generate(
    system_instruction: str,
    user_prompt: str,
    *,
    model: str = "gemini-1.5-flash",
) -> GeminiResponse:
    """
    Minimal Gemini adapter used by the clean pipeline (google.genai).

    Env:
      - GEMINI_API_KEY (or GOOGLE_API_KEY) must be set.
      - Optional: GEMINI_MODEL to override default model.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable is not set")

    # Prefer config default, allow env override
    try:
        import src.config as cfg
        model = getattr(cfg, "GEMINI_MODEL", model)
    except Exception:
        pass
    model = os.getenv("GEMINI_MODEL", model)
    if model.startswith("models/"):
        model = model[len("models/") :]

    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_instruction,
            "temperature": 0.0,
        },
    )

    raw = (getattr(resp, "text", "") or "").strip()

    parsed: Optional[Any] = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    return GeminiResponse(raw_text=raw, parsed_json=parsed)

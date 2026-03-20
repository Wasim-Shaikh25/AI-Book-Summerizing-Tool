from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class LLMResult:
    text: str
    raw: Any | None = None
    usage: dict[str, Any] | None = None
    model: str | None = None
    latency_ms: int | None = None


class BaseLLMProvider(Protocol):
    """
    Provider contract.

    Any model backend (Gemini, local Qwen, etc.) must implement this so that the rest
    of the codebase can stay provider-agnostic.
    """

    name: str  # e.g. "GEMINI", "QWEN"

    def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
    ) -> LLMResult:
        ...

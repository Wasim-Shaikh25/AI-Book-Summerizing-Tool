"""Ports (interfaces) used by application/domain code.

Concrete implementations live in infrastructure modules:
- LLMAdaptor providers implement LLM ports
- persistence/repositories implement repository ports
- app/observability implements trace/log ports
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol, Sequence


@dataclass(frozen=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    raw: Any | None = None


class LLMClientPort(Protocol):
    """Minimal LLM client contract used by the pipeline."""

    def complete(
        self,
        *,
        messages: Sequence[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool | None = None,
    ) -> LLMResponse: ...


class TraceLoggerPort(Protocol):
    """Optional, structured tracing interface."""

    def log_json(self, name: str, payload: Any) -> None: ...

    def log_text(self, name: str, text: str) -> None: ...


class TocRepositoryPort(Protocol):
    """Persistence contract for TOC data (narrow on purpose)."""

    def save_toc(self, book_id: str, toc: Any) -> None: ...

    def load_toc(self, book_id: str) -> Optional[Any]: ...


class TopicRepositoryPort(Protocol):
    def save_topics(self, book_id: str, topics: Iterable[Any]) -> None: ...

    def load_topics(self, book_id: str) -> Sequence[Any]: ...

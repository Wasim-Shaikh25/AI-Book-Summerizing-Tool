from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RewriteRequestTopic(BaseModel):
    topic_id: str
    title: str
    level: int
    raw_text: str


class RewriteResponse(BaseModel):
    topic_id: str
    title: str
    level: int
    rewritten_text: str


@dataclass(frozen=True)
class RewriteResult:
    topic_id: str
    title: str
    level: int
    rewritten_text: str


class RewriteEngine:
    """
    Placeholder: full-book / fragment rewrite is not implemented in this repo revision.
    """

    def __init__(self, _gemini_client: Optional[Any] = None) -> None:
        raise NotImplementedError("Rewrite engine not yet implemented.")

    def build_request(self, *, book_id: str, topic_id: str, title: str, level: int, raw_text: str) -> Dict[str, Any]:
        req = RewriteRequestTopic(
            topic_id=str(topic_id),
            title=str(title),
            level=int(level),
            raw_text=str(raw_text),
        )
        return req.model_dump()

    def build_prompt(self, request_json: Dict[str, Any]) -> str:
        raise NotImplementedError("Rewrite engine not yet implemented.")

    def rewrite(self, *, book_id: str, topic: Dict[str, Any]) -> RewriteResult:
        raise NotImplementedError("Rewrite engine not yet implemented.")

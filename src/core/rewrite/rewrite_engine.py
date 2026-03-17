from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, ValidationError

# Structural reset: Gemini removed. Rewrite engine temporarily disabled until replacement is implemented.
# from src.core.gemini.client import GeminiClient

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


# Structural reset: Gemini removed.
# Keep the RewriteEngine module importable, but disable runtime usage for now.
class RewriteEngine:
    """
    Rewrite Engine (strict fragment mode).

    - Accepts a topic node + raw text
    - Builds JSON request format
    - Calls GeminiClient (no business logic inside Gemini client)
    - Validates JSON response
    - Returns rewritten content
    """

    def __init__(self, gemini_client: Optional[Any] = None) -> None:
        raise NotImplementedError("Rewrite engine not yet implemented.")

    def build_request(self, *, book_id: str, topic_id: str, title: str, level: int, raw_text: str) -> Dict[str, Any]:
        # MODE A strict rewrite request format (topic object only; no wrapper).
        req = RewriteRequestTopic(
            topic_id=str(topic_id),
            title=str(title),
            level=int(level),
            raw_text=str(raw_text),
        )
        return req.model_dump()

    def build_prompt(self, request_json: Dict[str, Any]) -> str:
        # Centralized prompt store.
        from src.LLMAdaptor.client import LLMClient

        client = LLMClient.from_config()
        rendered = client.prompts.get("strict_fragment_rewrite")
        # Keep it as a single combined prompt string for this legacy engine shape.
        return rendered.system + "\n\n" + rendered.user.format(request_json=json.dumps(request_json, ensure_ascii=False))

    def rewrite(self, *, book_id: str, topic: Dict[str, Any]) -> RewriteResult:
        """
        topic must include: topic_id, title, level, raw_text
        """
        request_json = self.build_request(
            book_id=book_id,
            topic_id=str(topic["topic_id"]),
            title=str(topic["title"]),
            level=int(topic["level"]),
            raw_text=str(topic["raw_text"]),
        )
        prompt = self.build_prompt(request_json)

        try:
            data = self.gemini.generate_content(prompt, response_schema=RewriteResponse)
            if not isinstance(data, dict) or not data:
                raise RuntimeError("Empty/invalid Gemini response (post-parse).")

            validated = RewriteResponse.model_validate(data)
            return RewriteResult(
                topic_id=validated.topic_id,
                title=validated.title,
                level=validated.level,
                rewritten_text=validated.rewritten_text,
            )
        except (ValidationError, KeyError, TypeError) as e:
            logger.error("RewriteEngine: response validation failed: %s", str(e))
            raise

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, ValidationError

# Structural reset: Gemini removed. Rewrite engine temporarily disabled until replacement is implemented.
# from src.core.gemini.client import GeminiClient

logger = logging.getLogger(__name__)


STRICT_FRAGMENT_SYSTEM_PROMPT = """You are rewriting structured academic content.

STRICT RULES:

1. Use ONLY the provided raw_text.
2. Do NOT introduce external knowledge.
3. Do NOT reorganize sections.
4. Do NOT merge concepts.
5. Do NOT create new headings.
6. Preserve logical flow as in raw_text.
7. Improve clarity and grammar only.
8. Keep paragraph order unchanged.
9. Output JSON only.

No bullet conversion unless raw_text contains bullets.
No conceptual regrouping.

Request format:

{
  "topic_id": "...",
  "title": "...",
  "level": 1,
  "raw_text": "..."
}

Expected response:

{
  "topic_id": "...",
  "title": "...",
  "level": 1,
  "rewritten_text": "..."
}
"""


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
        # Enforce JSON-only output in prompt body as well (GeminiClient also sets response_mime_type).
        return (
            STRICT_FRAGMENT_SYSTEM_PROMPT
            + "\n\nRewrite the following JSON request. Return ONLY a JSON object that matches the expected response schema.\n\n"
            + json.dumps(request_json, ensure_ascii=False)
        )

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

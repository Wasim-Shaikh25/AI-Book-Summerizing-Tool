"""Two-stage intent: (1) route task, (2) refine user prompt for executor."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Optional, Union

from src.modules.generation.model_router import RewriteModelRouter
from src.modules.interaction.command_parser import CommandParser, IntentResult
from src.modules.interaction.intent_catalog import intent_options_for_prompt
from src.modules.interaction.prompt_refiner import refine_user_prompt, should_refine

logger = logging.getLogger(__name__)

_CLI_COMMANDS = frozenset({"exit", "quit", "help", "export"})

_VALID_TASKS = frozenset(
    {
        "rewrite_book",
        "summarize_book",
        "study_notes",
        "revision_notes",
        "explain_section",
        "question_answer",
        "export",
        "clarify",
    }
)
_VALID_SCOPES = frozenset({"full_book", "specific_topic", "single_question"})
_VALID_DEPTHS = frozenset({"very_short", "short", "medium", "detailed"})
_VALID_LANGUAGE = frozenset({"simple", "standard", "advanced"})
_VALID_FORMATS = frozenset({"paragraph", "bullet", "exam_oriented", "free"})

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)
_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")

_CLASSIFIER_SYSTEM = f"""You classify user requests about an ingested document (book, manual, act, report, treatise, etc.).
Your job is ROUTING ONLY — decide which pipeline to invoke. Do not write rewrite prompts here.

{intent_options_for_prompt()}

Return ONLY valid JSON with this schema:
{{
  "task_type": "<one of the task types above>",
  "scope": "full_book | specific_topic | single_question",
  "depth": "very_short | short | medium | detailed",
  "language_level": "simple | standard | advanced",
  "format_type": "paragraph | bullet | exam_oriented | free",
  "allow_external_knowledge": true or false,
  "brief_summary": "one-sentence restatement of user intent",
  "target_topics": ["topic names if user named specific sections"],
  "include_diagrams": true or false,
  "clarification_message": "only when task_type is clarify"
}}

Rules:
- rewrite_book / study_notes / revision_notes / summarize_book → full_book scope unless user names one topic
- explain_section → specific_topic scope; user wants ONE section/topic explained
- question_answer → single_question unless user names a chapter area
- export → user only wants download, no generation
- clarify → too vague to route
- allow_external_knowledge=false for book rewrite tasks; true for QA unless user says book-only
- Do NOT include rewrite_format or detailed output templates in this response
- Examples: legal acts (BNS, CPC), medical textbooks, engineering manuals, business reports, research papers — all use same routing
"""


def use_llm_intent() -> bool:
    raw = os.environ.get("USE_LLM_INTENT", "1").strip().lower()
    return raw not in {"0", "false", "no", "n", "off"}


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    for pattern in (_JSON_BLOCK, _JSON_OBJECT):
        match = pattern.search(raw)
        if not match:
            continue
        blob = match.group(1) if pattern is _JSON_BLOCK else match.group(0)
        try:
            data = json.loads(blob)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _coerce_str(value: Any, default: str, allowed: frozenset[str]) -> str:
    text = str(value or default).strip().lower()
    return text if text in allowed else default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return default


def intent_from_llm_payload(payload: dict[str, Any], *, user_input: str) -> IntentResult:
    """Build IntentResult from stage-1 classifier JSON (before refinement)."""
    task = _coerce_str(payload.get("task_type"), "question_answer", _VALID_TASKS)
    scope = _coerce_str(payload.get("scope"), "single_question", _VALID_SCOPES)

    if task in {"rewrite_book", "summarize_book", "study_notes", "revision_notes"}:
        scope = "full_book" if scope != "specific_topic" else scope
    elif task == "explain_section":
        scope = "specific_topic"
    elif task == "question_answer":
        scope = "single_question" if scope == "full_book" else scope

    brief = str(payload.get("brief_summary") or payload.get("normalized_query") or user_input).strip()
    topics_raw = payload.get("target_topics") or []
    topics = [str(t).strip() for t in topics_raw if str(t).strip()] if isinstance(topics_raw, list) else []

    return IntentResult(
        task_type=task,
        scope=scope,
        depth=_coerce_str(payload.get("depth"), "medium", _VALID_DEPTHS),
        language_level=_coerce_str(payload.get("language_level"), "standard", _VALID_LANGUAGE),
        format_type=_coerce_str(payload.get("format_type"), "free", _VALID_FORMATS),
        allow_external_knowledge=_coerce_bool(payload.get("allow_external_knowledge"), task == "question_answer"),
        normalized_query=brief or user_input,
        original_user_input=user_input.strip(),
        target_topics=topics,
        include_diagrams=_coerce_bool(payload.get("include_diagrams"), False),
        clarification_message=str(payload.get("clarification_message") or "").strip(),
        routing_method="llm",
    )


def apply_prompt_refinement(intent: IntentResult, user_input: str) -> IntentResult:
    """Stage 2 — polish wording for logging; executors use original_user_input."""
    if not should_refine(intent):
        return intent

    refined = refine_user_prompt(user_input, intent)
    return intent.model_copy(
        update={
            "refined_instruction": refined.refined_instruction,
            "refinement_method": refined.method,
        }
    )


class IntentRouter:
    """Route user text → classify task → refine prompt → IntentResult."""

    def __init__(
        self,
        *,
        use_llm: bool | None = None,
        classifier: Callable[[str], dict[str, Any] | None] | None = None,
        skip_refinement: bool | None = None,
    ) -> None:
        self._use_llm = use_llm if use_llm is not None else use_llm_intent()
        self._fallback = CommandParser()
        self._classifier = classifier
        self._router: RewriteModelRouter | None = None
        if skip_refinement is None:
            raw = os.environ.get("INTENT_SKIP_REFINEMENT", "").strip().lower()
            self._skip_refinement = raw in {"1", "true", "yes", "y", "on"}
        else:
            self._skip_refinement = skip_refinement

    def _get_router(self) -> RewriteModelRouter:
        if self._router is None:
            self._router = RewriteModelRouter()
        return self._router

    def parse_intent(self, user_input: str) -> Optional[Union[IntentResult, str]]:
        user_input = user_input.strip()
        if not user_input:
            return None

        cmd = user_input.lower()
        if cmd in _CLI_COMMANDS:
            return self._fallback.parse_intent(user_input)

        if not self._use_llm:
            intent = self._fallback.parse_intent(user_input)
            if isinstance(intent, IntentResult):
                intent.routing_method = "rules"
                intent.refinement_method = "rules"
                intent.refined_instruction = user_input
                intent.original_user_input = user_input
            return intent

        try:
            payload = self._classify(user_input)
            if payload:
                intent = intent_from_llm_payload(payload, user_input=user_input)
                if not self._skip_refinement:
                    intent = apply_prompt_refinement(intent, user_input)
                elif not intent.refined_instruction:
                    intent = intent.model_copy(
                        update={
                            "refined_instruction": user_input,
                            "refinement_method": "passthrough",
                            "original_user_input": user_input.strip(),
                        }
                    )
                return intent
        except Exception as exc:
            logger.warning("LLM intent routing failed, using rules fallback: %s", exc)

        intent = self._fallback.parse_intent(user_input)
        if isinstance(intent, IntentResult):
            intent.routing_method = "rules"
            intent.refinement_method = "rules"
            intent.refined_instruction = user_input
            intent.original_user_input = user_input
        return intent

    def _classify(self, user_input: str) -> dict[str, Any] | None:
        if self._classifier is not None:
            return self._classifier(user_input)

        result = self._get_router().generate(
            system_prompt=_CLASSIFIER_SYSTEM,
            user_prompt=f"User message:\n{user_input}",
            max_tokens=400,
        )
        text = (result.get("text") or "").strip()
        if not text:
            return None
        payload = _extract_json(text)
        if not payload:
            logger.warning("LLM intent response was not valid JSON: %s", text[:200])
        return payload

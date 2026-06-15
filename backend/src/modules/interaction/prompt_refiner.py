"""Stage 2 — lightly polish user input without changing core requirements."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from src.modules.interaction.command_parser import IntentResult

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)
_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")

_REFINER_SYSTEM = """You polish a classified user request for clarity. Your job is NOT to redesign the output format.

Return ONLY valid JSON:
{
  "refined_instruction": "a lightly edited version of the user's message — same requirements, clearer wording"
}

Rules:
- PRESERVE the user's core requirements: length, tone, format preferences, and scope they stated.
- Do NOT add bullets, bold subheadings, templates, or section layouts the user did not ask for.
- Do NOT contradict the user (e.g. if they said "no bullets", do not add bullets).
- Do NOT expand vague requests into long format specs — only fix grammar and make implied intent explicit.
- For question_answer or explain_section: keep it as a clear question or explain request.
- For full-book rewrite tasks: keep coverage expectations the user stated; do not invent new structure.
- If the user message is already clear, return it nearly unchanged.
- Respect the configured notes export style when mentioned in the user block (book = continuous prose).
"""


@dataclass(frozen=True, slots=True)
class RefineResult:
    refined_instruction: str
    rewrite_format: str
    method: str


def refiner_backend() -> str:
    from src.shared.llm_provider import intent_refiner_backend

    return intent_refiner_backend()


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


def _export_style_hint() -> str:
    try:
        from src.shared.notes_export_style import resolve_notes_export_style

        style = resolve_notes_export_style()
        if style == "book":
            return "book (continuous prose textbook layout — not bullet-heavy study notes)"
        return style
    except Exception:
        return "study"


def _passthrough(user_input: str, intent: IntentResult) -> RefineResult:
    return RefineResult(
        refined_instruction=user_input.strip(),
        rewrite_format="",
        method="passthrough",
    )


class OpenAIPromptRefiner:
    """Polish user wording after routing — no format template injection."""

    def __init__(self) -> None:
        self._router = None

    def _get_router(self):
        if self._router is None:
            from src.modules.generation.model_router import RewriteModelRouter

            self._router = RewriteModelRouter()
        return self._router

    def refine(self, user_input: str, intent: IntentResult) -> RefineResult:
        method = refiner_backend()
        user_block = (
            f"Original user message:\n{user_input}\n\n"
            f"Classified intent (routing metadata only — do not override user wording with these):\n"
            f"  task_type: {intent.task_type}\n"
            f"  scope: {intent.scope}\n"
            f"  depth: {intent.depth}\n"
            f"  language_level: {intent.language_level}\n"
            f"  format_type: {intent.format_type}\n"
            f"  include_diagrams: {intent.include_diagrams}\n"
            f"  target_topics: {', '.join(intent.target_topics) or '(none)'}\n"
            f"  notes_export_style: {_export_style_hint()}\n"
        )
        result = self._get_router().generate(
            system_prompt=_REFINER_SYSTEM,
            user_prompt=user_block,
            max_tokens=500,
        )
        text = (result.get("text") or "").strip()
        payload = _extract_json(text) if text else None
        if payload:
            refined = str(payload.get("refined_instruction") or "").strip()
            if refined:
                return RefineResult(refined_instruction=refined, rewrite_format="", method=method)
        if text and not payload:
            return RefineResult(refined_instruction=text[:2000], rewrite_format="", method=method)
        return _passthrough(user_input, intent)


_openai_refiner: OpenAIPromptRefiner | None = None


def refine_user_prompt(user_input: str, intent: IntentResult) -> RefineResult:
    """Polish user text after routing. Skipped for export/clarify."""
    if intent.task_type in {"export", "clarify"}:
        return _passthrough(user_input, intent)

    backend = refiner_backend()
    if backend in {"0", "off", "false", "none", "passthrough", "flan", "bigbird"}:
        if backend in {"flan", "bigbird"}:
            logger.warning("INTENT_REFINER_BACKEND=%s is removed; using passthrough", backend)
        return _passthrough(user_input, intent)

    global _openai_refiner

    if _openai_refiner is None:
        _openai_refiner = OpenAIPromptRefiner()
    return _openai_refiner.refine(user_input, intent)


def should_refine(intent: IntentResult) -> bool:
    return intent.task_type not in {"export", "clarify"}

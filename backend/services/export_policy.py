"""Word export decision logic for chat responses."""

from __future__ import annotations

import re

from auth.config import get_auth_settings
from src.modules.interaction.command_parser import IntentResult

REWRITE_TASKS = frozenset(
    {"rewrite_book", "summarize_book", "study_notes", "revision_notes"}
)

WORD_REQUEST_PATTERNS = (
    r"\b(word\s*file|docx|\.docx)\b",
    r"\b(export|download|save)\b.*\b(word|docx)\b",
    r"\bgive\s+me\b.*\b(word|docx)\b",
    r"\bprovide\b.*\b(word|docx)\b",
)


def user_requests_word_export(text: str) -> bool:
    lowered = text.lower().strip()
    return any(re.search(p, lowered) for p in WORD_REQUEST_PATTERNS)


def is_full_rewrite_intent(intent: IntentResult) -> bool:
    return intent.task_type in REWRITE_TASKS and intent.scope == "full_book"


def should_auto_docx_for_qa(answer: str) -> bool:
    limit = get_auth_settings().chat_docx_char_limit
    return len(answer or "") > limit


def resolve_export_mode(
    intent: IntentResult,
    *,
    answer: str | None,
    user_text: str,
    explicit_word_request: bool | None = None,
) -> tuple[bool, str]:
    """
    Returns (needs_docx, reason).
    reason: always | qa_length | user_request | chat_only | rewrite
    """
    if explicit_word_request is None:
        explicit_word_request = user_requests_word_export(user_text)

    if is_full_rewrite_intent(intent):
        return True, "rewrite"

    if intent.task_type == "question_answer":
        if explicit_word_request and answer:
            return True, "user_request"
        if answer and should_auto_docx_for_qa(answer):
            return True, "qa_length"
        return False, "chat_only"

    if explicit_word_request and answer:
        return True, "user_request"

    return False, "chat_only"

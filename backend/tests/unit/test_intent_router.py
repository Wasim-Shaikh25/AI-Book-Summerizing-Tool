"""Tests for LLM intent router and dynamic rewrite prompts."""

from __future__ import annotations

import pytest

from src.modules.generation.rewrite_prompts import (
    build_dynamic_rewrite_system_prompt,
    legacy_regex_enabled,
    resolve_rewrite_profile,
    rewrite_system_prompt,
)
from src.modules.interaction.command_parser import IntentResult
from src.modules.interaction.intent_router import (
    IntentRouter,
    _extract_json,
    intent_from_llm_payload,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "USE_LLM_INTENT",
        "INTENT_LEGACY_REGEX",
        "EXAM_ORIENTED",
        "COMPACT_EXAM",
        "REWRITE_INCLUDE_DIAGRAMS",
        "REWRITE_USER_INSTRUCTION",
    ):
        monkeypatch.delenv(key, raising=False)


def test_extract_json_from_codeblock() -> None:
    raw = 'Here is the result:\n```json\n{"task_type": "question_answer"}\n```'
    data = _extract_json(raw)
    assert data == {"task_type": "question_answer"}


def test_intent_from_llm_payload_rewrite() -> None:
    payload = {
        "task_type": "study_notes",
        "scope": "full_book",
        "depth": "short",
        "language_level": "simple",
        "format_type": "free",
        "allow_external_knowledge": False,
        "brief_summary": "Create short exam notes in simple English",
        "target_topics": [],
        "include_diagrams": False,
    }
    intent = intent_from_llm_payload(payload, user_input="make study notes")
    assert intent.task_type == "study_notes"
    assert intent.scope == "full_book"
    assert intent.routing_method == "llm"
    assert intent.rewrite_format == ""


def test_intent_router_uses_classifier_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTENT_REFINER_BACKEND", "passthrough")

    def _classify(text: str) -> dict:
        if "rewrite" in text.lower():
            return {
                "task_type": "rewrite_book",
                "scope": "full_book",
                "depth": "medium",
                "language_level": "simple",
                "format_type": "free",
                "allow_external_knowledge": False,
                "brief_summary": text,
            }
        return {
            "task_type": "question_answer",
            "scope": "single_question",
            "depth": "medium",
            "language_level": "standard",
            "format_type": "paragraph",
            "allow_external_knowledge": True,
            "brief_summary": text,
        }

    router = IntentRouter(use_llm=True, classifier=_classify)
    rewrite = router.parse_intent("rewrite the book in simple English")
    assert isinstance(rewrite, IntentResult)
    assert rewrite.task_type == "rewrite_book"
    assert rewrite.routing_method == "llm"
    assert rewrite.refined_instruction

    qa = router.parse_intent("explain Article 14 equality")
    assert isinstance(qa, IntentResult)
    assert qa.task_type == "question_answer"


def test_intent_router_fallback_when_llm_disabled() -> None:
    router = IntentRouter(use_llm=False)
    intent = router.parse_intent("rewrite the book in simple English")
    assert isinstance(intent, IntentResult)
    assert intent.task_type == "rewrite_book"
    assert intent.routing_method == "rules"


def test_dynamic_prompt_uses_user_instruction_not_refiner_format() -> None:
    intent = IntentResult(
        task_type="study_notes",
        scope="full_book",
        depth="short",
        language_level="simple",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="short exam notes",
        original_user_input="short exam notes no bullets",
        refined_instruction="Short paragraph-style exam notes in simple English.",
        rewrite_format="Short paragraphs; bullets only for lists of 3+ items.",
        routing_method="llm",
        refinement_method="openai",
    )
    prompt = rewrite_system_prompt(user_instruction="", intent=intent)
    assert "short exam notes no bullets" in prompt
    assert "Output format (follow exactly)" not in prompt
    assert "bullets only for lists" not in prompt
    assert "HARD LIMIT: 4–6 bullets" not in prompt
    assert "OUTPUT FORMAT (paragraph-first" not in prompt


def test_default_prompt_does_not_force_key_points() -> None:
    prompt = rewrite_system_prompt(user_instruction="create topic wise notes in simple english")
    assert "### Key Points" not in prompt
    assert "Do NOT impose fixed templates" in prompt


def test_last_moment_instruction_no_longer_forces_compact_template() -> None:
    prompt = rewrite_system_prompt(
        user_instruction="create topic wise exam oriented notes in very simple english and short for last moment preparation"
    )
    assert "HARD LIMIT: 4–6 bullets" not in prompt
    assert "Do NOT add a Quick Revision section" not in prompt


def test_legacy_regex_still_available_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTENT_LEGACY_REGEX", "1")
    assert legacy_regex_enabled() is True
    profile = resolve_rewrite_profile(
        "create exam prep notes with key points for last moment preparation"
    )
    assert profile.exam_oriented is True
    assert profile.compact is True
    prompt = rewrite_system_prompt(user_instruction="create exam prep notes with key points for last moment")
    assert "### Key Points" in prompt


def test_resolve_rewrite_profile_from_llm_intent() -> None:
    intent = IntentResult(
        task_type="rewrite_book",
        scope="full_book",
        depth="detailed",
        language_level="standard",
        format_type="free",
        allow_external_knowledge=False,
        normalized_query="detailed notes",
        include_diagrams=True,
        routing_method="llm",
    )
    profile = resolve_rewrite_profile("", intent=intent)
    assert profile.depth == "detailed"
    assert profile.include_diagrams is True
    assert profile.exam_oriented is False
    assert profile.max_tokens >= 2800


def test_build_dynamic_includes_guardrails() -> None:
    prompt = build_dynamic_rewrite_system_prompt(
        user_instruction="short bullets only",
        intent=IntentResult(
            task_type="rewrite_book",
            scope="full_book",
            depth="short",
            language_level="simple",
            format_type="free",
            allow_external_knowledge=False,
            normalized_query="short bullets only",
            original_user_input="short bullets only",
            rewrite_format="3 bullets per section",
            routing_method="llm",
        ),
    )
    assert "Use only the provided source text" in prompt
    assert "short bullets only" in prompt
    assert "3 bullets per section" not in prompt

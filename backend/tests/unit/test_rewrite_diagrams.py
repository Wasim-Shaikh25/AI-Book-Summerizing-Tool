"""Tests for dynamic rewrite profile (format + length from user input)."""

from __future__ import annotations

import pytest

from src.modules.generation.rewrite_prompts import (
    infer_content_depth,
    is_compact_exam_mode,
    is_exam_oriented_mode,
    legacy_regex_enabled,
    normalize_rewritten_section,
    resolve_rewrite_profile,
    rewrite_system_prompt,
    user_requests_diagrams,
    user_requests_exam_notes,
)
from src.modules.interaction.command_parser import IntentResult


@pytest.fixture(autouse=True)
def _clear_rewrite_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "INTENT_LEGACY_REGEX",
        "EXAM_ORIENTED",
        "COMPACT_EXAM",
        "REWRITE_INCLUDE_DIAGRAMS",
        "REWRITE_USER_INSTRUCTION",
        "REWRITE_ASK",
        "PIPELINE_REWRITE_ASK",
    ):
        monkeypatch.delenv(key, raising=False)


def test_default_profile_is_generic_not_exam() -> None:
    profile = resolve_rewrite_profile("rewrite this chapter in clear notes")
    assert profile.exam_oriented is False
    assert profile.compact is False
    assert profile.depth == "medium"
    assert profile.max_tokens == 1800


def test_exam_profile_only_with_legacy_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTENT_LEGACY_REGEX", "1")
    profile = resolve_rewrite_profile("create exam prep notes with key points for revision")
    assert profile.exam_oriented is True
    assert "Key Points" in rewrite_system_prompt(user_instruction="create exam prep notes with key points")


def test_generic_prompt_has_no_forced_key_points() -> None:
    prompt = rewrite_system_prompt(user_instruction="explain main ideas simply")
    assert "### Key Points" not in prompt
    assert "### Quick Revision" not in prompt
    assert "Do NOT impose fixed templates" in prompt


def test_depth_short_from_user_wording() -> None:
    assert infer_content_depth("brief simple notes, no extra details") == "short"
    profile = resolve_rewrite_profile("short simple notes, no extra details")
    assert profile.max_tokens == 1000


def test_depth_detailed_from_user_wording() -> None:
    profile = resolve_rewrite_profile("detailed comprehensive notes covering everything")
    assert profile.depth == "detailed"
    assert profile.max_tokens == 2800


def test_user_requests_diagrams_from_instruction() -> None:
    assert user_requests_diagrams("add mermaid diagrams for better understanding")
    assert not user_requests_diagrams("short notes only")


def test_rewrite_system_prompt_includes_diagram_rules() -> None:
    prompt = rewrite_system_prompt(user_instruction="use diagrams")
    assert "DIAGRAM RULES" in prompt


def test_normalize_rewritten_section_fixes_single_backtick_mermaid() -> None:
    raw = """- One fact

`mermaid
flowchart TD
    A --> B
`"""
    out = normalize_rewritten_section(raw)
    assert "```mermaid" in out
    assert out.count("```") >= 2


def test_study_notes_without_exam_keyword_stays_generic() -> None:
    assert user_requests_exam_notes("create study notes from chapter 1") is False
    assert is_exam_oriented_mode(user_instruction="create study notes from chapter 1") is False
    assert is_compact_exam_mode(user_instruction="create study notes from chapter 1") is False


def test_similar_adjacent_sections_get_deduplication_note() -> None:
    from src.modules.generation.rewrite_prompts import build_section_user_prompt_with_context

    prompt = build_section_user_prompt_with_context(
        user_instruction="short notes",
        heading="B. Position after the Forty-second Amendment (1976)",
        source_text="Source about 42nd amendment.",
        prev_heading="B. Position after the Forty-fourth Amendment",
        prev_overlap="",
    )
    assert "Do NOT repeat" in prompt
    assert "unique to THIS section" in prompt


def test_llm_intent_depth_overrides_keywords() -> None:
    intent = IntentResult(
        task_type="rewrite_book",
        scope="full_book",
        depth="very_short",
        language_level="simple",
        format_type="free",
        allow_external_knowledge=False,
        normalized_query="short cram notes",
        routing_method="llm",
    )
    profile = resolve_rewrite_profile("", intent=intent)
    assert profile.depth == "very_short"
    assert profile.compact is False
    assert legacy_regex_enabled() is False

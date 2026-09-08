"""Tests for rewrite prompt assembly — subheadings, study/book modes, TOC fallback."""

from __future__ import annotations

from src.modules.generation.parallel_rewrite import build_rewrite_jobs
from src.modules.generation.rewrite_prompts import (
    build_dynamic_rewrite_system_prompt,
    build_section_user_prompt_with_context,
)
from src.shared.document_format_style import universal_prose_rules


def test_sub_labels_from_dict_subheadings() -> None:
    sections = [
        {
            "section_id": "S1",
            "heading": "Rights",
            "text": "body",
            "subheadings": [
                {"heading": "Art. 14", "line_id": 1, "fragment": {}},
                {"heading": "Art. 15", "line_id": 2, "fragment": {}},
            ],
        },
    ]
    jobs = build_rewrite_jobs(sections, max_source_chars=5000, overlap_chars=0)
    assert jobs[0].subheadings == ("Art. 14", "Art. 15")


def test_sub_labels_from_string_subheadings() -> None:
    sections = [
        {
            "section_id": "S1",
            "heading": "Rights",
            "text": "body",
            "subheadings": ["Art. 14", "Art. 15"],
        },
    ]
    jobs = build_rewrite_jobs(sections, max_source_chars=5000, overlap_chars=0)
    assert jobs[0].subheadings == ("Art. 14", "Art. 15")


def test_long_section_trigger_no_subheadings(monkeypatch) -> None:
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    long_text = "x" * 1900
    prompt = build_section_user_prompt_with_context(
        user_instruction="rewrite",
        heading="Section A",
        source_text=long_text,
    )
    assert "LONG SECTION" in prompt


def test_long_section_no_trigger_with_subheadings(monkeypatch) -> None:
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    long_text = "x" * 1900
    prompt = build_section_user_prompt_with_context(
        user_instruction="rewrite",
        heading="Section A",
        source_text=long_text,
        subheadings=["Part One"],
    )
    assert "LONG SECTION" not in prompt
    assert "These sub-topics were detected" in prompt


def test_study_mode_prompt_uses_headings(monkeypatch) -> None:
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    prompt = build_section_user_prompt_with_context(
        user_instruction="study notes",
        heading="Section A",
        source_text="short body",
    )
    assert "Use ### for each distinct sub-topic" in prompt
    assert "**bold** label" not in prompt


def test_book_mode_prompt_uses_prose(monkeypatch) -> None:
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "book")
    prompt = build_dynamic_rewrite_system_prompt(user_instruction="rewrite into notes")
    assert "PROSE FIRST" in prompt
    assert "continuous paragraphs" in prompt


def test_universal_prose_rules_book() -> None:
    text = universal_prose_rules(book_style=True)
    assert "continuous paragraphs" in text


def test_universal_prose_rules_study() -> None:
    text = universal_prose_rules(book_style=False)
    assert "### subheadings" in text

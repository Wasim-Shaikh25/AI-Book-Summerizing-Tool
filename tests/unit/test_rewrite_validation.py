"""Tests for rewrite validation and section-id mapping."""
from __future__ import annotations

from src.modules.export.docx_notes_exporter import (
    parse_markdown_sections,
    rewritten_map_from_section_bodies,
)
from src.modules.generation.rewrite_validation import (
    heading_similarity,
    normalize_heading,
    validate_rewrite_coverage,
)


def test_normalize_heading_strips_mojibake() -> None:
    assert normalize_heading("Legal Position And Utility Of A PreambleÆ") == normalize_heading(
        "Legal Position And Utility Of A Preamble"
    )


def test_heading_similarity_fuzzy() -> None:
    assert heading_similarity("FUNDAMENTAL RIGHTS (Articles 12-33)", "Fundamental Rights (Articles 12-33)") >= 0.9


def test_parse_section_id_tag() -> None:
    md = """# Table of Contents

# Intro

## THE PREAMBLE <!-- sid:S1 -->

- bullet one
"""
    by_h, by_sid = parse_markdown_sections(md)
    assert "S1" in by_sid
    assert "bullet one" in by_sid["S1"]
    assert "THE PREAMBLE" in by_h


def test_parse_numbered_section_heading() -> None:
    md = """# Table of Contents

# Fundamental Rights

## 1. Equality before the law (Art. 14)

- equality note
"""
    by_h, _ = parse_markdown_sections(md)
    assert "1. Equality before the law (Art. 14)" in by_h


def test_rewritten_map_uses_section_id_first() -> None:
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Intro",
                "sections": [
                    {"section_id": "S1", "heading": "Different Title In 15e"},
                    {"section_id": "S2", "heading": "Second"},
                ],
            }
        ]
    }
    by_sid = {"S1": "body one", "S2": "body two"}
    mapped = rewritten_map_from_section_bodies(hierarchy, {}, by_section_id=by_sid)
    assert mapped == {"S1": "body one", "S2": "body two"}


def test_validate_rewrite_coverage_pass() -> None:
    hierarchy = {
        "chapters": [
            {"heading": "A", "sections": [{"section_id": "S1", "heading": "One", "subheadings": []}]}
        ]
    }
    report = validate_rewrite_coverage(hierarchy, {"S1": "notes here"})
    assert report.ok
    assert report.coverage_ratio == 1.0

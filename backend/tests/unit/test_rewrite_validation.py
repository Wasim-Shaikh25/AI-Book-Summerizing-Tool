"""Tests for rewrite validation and section-id mapping."""
from __future__ import annotations

from src.modules.export.docx_notes_exporter import (
    parse_markdown_sections,
    resolve_rewritten_map,
    rewritten_map_from_section_bodies,
)
from src.modules.export.document_formatter import chapter_blocks_from_hierarchy
from src.modules.generation.rewrite_validation import (
    dedupe_consecutive_section_headings,
    heading_similarity,
    normalize_heading,
    strip_redundant_section_heading,
    strip_section_id_tags,
    validate_rewrite_coverage,
)


def test_normalize_heading_strips_mojibake() -> None:
    assert normalize_heading("Legal Position And Utility Of A PreambleÆ") == normalize_heading(
        "Legal Position And Utility Of A Preamble"
    )


def test_heading_similarity_fuzzy() -> None:
    assert heading_similarity("FUNDAMENTAL RIGHTS (Articles 12-33)", "Fundamental Rights (Articles 12-33)") >= 0.9


def test_dedupe_consecutive_section_headings() -> None:
    md = """## Equality before the law (Art. 14) <!-- sid:S25 -->

## Equality before the Law (Art. 14)

Body text."""
    out = dedupe_consecutive_section_headings(md)
    assert out.count("Equality before") == 1
    assert "Body text" in out


def test_strip_redundant_section_heading_removes_llm_echo() -> None:
    body = "## Equality before the Law (Art. 14)\n\nArt. 14 states equality."
    out = strip_redundant_section_heading(body, "Equality before the law (Art. 14)")
    assert "## Equality" not in out.splitlines()[0]
    assert "Art. 14 states" in out


def test_strip_section_id_tags_removes_internal_markers() -> None:
    raw = "## Equality before the law <!-- sid:S132 -->\n\n- fact"
    out = strip_section_id_tags(raw)
    assert "<!-- sid:" not in out
    assert "Equality before the law" in out


def test_chapter_blocks_include_sid_tags_for_audit_join() -> None:
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Rights",
                "sections": [{"section_id": "S1", "heading": "Article 14"}],
            }
        ]
    }
    blocks, _ = chapter_blocks_from_hierarchy(hierarchy, {"S1": "Art. 14 guarantees equality before the law."})
    assert blocks
    assert "<!-- sid:S1 -->" in blocks[0]
    assert "Art. 14 guarantees" in blocks[0]


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


def test_parse_markdown_sections_reads_h3_sid_tags() -> None:
    md = """# Table of Contents

# Chapter

## Bundle label

### Alpha <!-- sid:S2 -->

body two
"""
    by_h, by_sid = parse_markdown_sections(md)
    assert by_sid.get("S2", "").startswith("body two")


def test_assemble_notes_document_preserves_section_id_tags() -> None:
    from src.modules.export.document_formatter import BookCoverMeta, assemble_notes_document

    cover = BookCoverMeta(title="Test Book")
    blocks = ["# Chapter\n\n## Section One <!-- sid:S1 -->\n\nBody text here."]
    doc = assemble_notes_document(
        cover=cover,
        toc_entries=[],
        chapter_blocks=blocks,
        include_toc=False,
    )
    assert "<!-- sid:S1 -->" in doc
    assert "Body text here." in doc


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


def test_resolve_rewritten_map_joins_by_sid_when_display_title_differs() -> None:
    """Display title in export MD can differ from raw hierarchy heading; sid tag is authoritative."""
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "BNS Overview",
                "sections": [
                    {
                        "section_id": "S44",
                        "heading": "Section 309: Robbery. — Fund held and administered by the Employee",
                    },
                ],
            }
        ]
    }
    md = """# Table of Contents

# BNS Overview

## Robbery and Fund Administration <!-- sid:S44 -->

Robbery involves taking property by force or threat.
"""
    mapped = resolve_rewritten_map(hierarchy, md_text=md)
    assert mapped.get("S44", "").startswith("Robbery involves")


def test_validate_rewrite_coverage_pass() -> None:
    hierarchy = {
        "chapters": [
            {"heading": "A", "sections": [{"section_id": "S1", "heading": "One", "subheadings": []}]}
        ]
    }
    report = validate_rewrite_coverage(hierarchy, {"S1": "notes here"})
    assert report.ok
    assert report.coverage_ratio == 1.0

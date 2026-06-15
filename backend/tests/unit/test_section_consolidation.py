"""Unit tests for universal section consolidation."""
from __future__ import annotations

from src.modules.structure.section_consolidation import (
    consolidate_chapter_sections,
    is_low_value_heading,
    _best_merged_title,
)


def test_is_low_value_heading_flags_chapter_and_illustration() -> None:
    assert is_low_value_heading("CHAPTER VI: OF OFFENCES AFFECTING THE HUMAN BODY")
    assert is_low_value_heading("Illustrations")
    assert is_low_value_heading("Section topic (p. 7)")


def test_best_merged_title_prefers_numbered_section() -> None:
    title = _best_merged_title(
        "CHAPTER XIII",
        "198. Public servant disobeying law, with intent to cause injury",
    )
    assert "198" in title


def test_consolidate_chapter_sections_merges_thin_neighbors() -> None:
    sections = [
        {
            "section_id": "S1",
            "heading": "CHAPTER VI: OF OFFENCES AFFECTING THE HUMAN BODY",
            "fragment": {"chars": 0, "preview": ""},
            "subheadings": [],
        },
        {
            "section_id": "S2",
            "heading": "Section 100: Culpable homicide",
            "fragment": {"chars": 450, "preview": "Whoever causes death..."},
            "subheadings": [],
        },
        {
            "section_id": "S3",
            "heading": "Illustrations",
            "fragment": {"chars": 30, "preview": "A shoots B"},
            "subheadings": [],
        },
    ]
    out, merges = consolidate_chapter_sections(sections)
    assert merges >= 1
    assert len(out) < len(sections)
    assert any("100" in str(s.get("heading") or "") for s in out)


def test_consolidate_does_not_merge_backward_page_order() -> None:
    # Sections carry enough body to avoid thin-junk dropping; the focus is that a
    # backward page jump (191 -> 186) must NOT trigger a merge.
    body = "x" * 300
    sections = [
        {
            "section_id": "S1",
            "heading": "Section 260: Omission",
            "page_number": 191,
            "fragment": {"chars": len(body), "preview": body},
            "subheadings": [],
        },
        {
            "section_id": "S2",
            "heading": "Punishment for Omission",
            "page_number": 186,
            "fragment": {"chars": len(body), "preview": body},
            "subheadings": [],
        },
    ]
    out, merges = consolidate_chapter_sections(sections)
    assert merges == 0
    assert len(out) == 2

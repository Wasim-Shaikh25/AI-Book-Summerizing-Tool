"""Tests for related-chapter consolidation."""

from __future__ import annotations

from unittest.mock import patch

from src.modules.structure.final_structuring.chapter_cohesion import (
    coalesce_regroup_assignments,
    consolidate_chapter_hierarchy,
    merge_related_adjacent_chapters,
)


def test_coalesce_regroup_assignments_merges_related_starts() -> None:
    sections = [
        {"section_id": "S1", "heading": "Muslim Marriage", "fragment": {"preview": "nikah rules"}},
        {"section_id": "S2", "heading": "Registration of Marriage", "fragment": {"preview": "registration"}},
        {"section_id": "S3", "heading": "Khula", "fragment": {"preview": "divorce by wife"}},
    ]
    assignments = [
        {"section_id": "S1", "chapter_title": "Marriage", "is_chapter_start": True},
        {"section_id": "S2", "chapter_title": "Registration", "is_chapter_start": True},
        {"section_id": "S3", "chapter_title": "Khula", "is_chapter_start": True},
    ]
    with patch(
        "src.modules.structure.final_structuring.chapter_cohesion.sections_are_related",
        return_value=True,
    ):
        changed = coalesce_regroup_assignments(assignments, sections)
    assert changed >= 2
    assert assignments[1]["is_chapter_start"] is False
    assert assignments[2]["is_chapter_start"] is False


def test_merge_related_adjacent_chapters_combines_thin_tail() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Muslim Marriage Law",
            "sections": [
                {"section_id": "S1", "heading": "Marriage", "fragment": {"preview": "muslim marriage"}},
                {"section_id": "S2", "heading": "Mahr", "fragment": {"preview": "dower payment"}},
            ],
        },
        {
            "chapter_id": "C2",
            "heading": "Khula",
            "sections": [{"section_id": "S3", "heading": "Khula", "fragment": {"preview": "wife divorce khula"}}],
        },
    ]
    with patch(
        "src.modules.structure.final_structuring.chapter_cohesion.chapters_are_related",
        return_value=True,
    ):
        merged, count = merge_related_adjacent_chapters(chapters, min_sections=3, max_sections=12)
    assert count == 1
    assert len(merged) == 1
    assert len(merged[0]["sections"]) == 3


def test_consolidate_keeps_module_break() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Intro",
            "sections": [{"section_id": "S1", "heading": "A", "fragment": {"chars": 50}}],
        },
        {
            "chapter_id": "C2",
            "heading": "MODULE 4:",
            "sections": [{"section_id": "S2", "heading": "B", "fragment": {"chars": 50}}],
        },
    ]
    out, stats = consolidate_chapter_hierarchy(chapters, min_sections=3, min_chars=400)
    assert len(out) == 2
    assert stats["related_merged"] == 0

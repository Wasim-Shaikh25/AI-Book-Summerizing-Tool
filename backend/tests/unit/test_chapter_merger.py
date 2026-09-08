"""Tests for chapter merge pass."""

from __future__ import annotations

from src.modules.structure.final_structuring.chapter_merger import merge_undersized_chapters


def test_merge_singleton_chapters() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Topic A",
            "sections": [{"section_id": "S1", "heading": "A", "fragment": {"chars": 200}}],
        },
        {
            "chapter_id": "C2",
            "heading": "Topic B",
            "sections": [{"section_id": "S2", "heading": "B", "fragment": {"chars": 100}}],
        },
        {
            "chapter_id": "C3",
            "heading": "Topic C",
            "sections": [
                {"section_id": "S3", "heading": "C1", "fragment": {"chars": 300}},
                {"section_id": "S4", "heading": "C2", "fragment": {"chars": 300}},
            ],
        },
    ]
    merged, count = merge_undersized_chapters(chapters, min_sections=2, min_chars=400)
    assert count >= 1
    assert len(merged) == 2
    assert sum(len(c.get("sections") or []) for c in merged) == 4


def test_keeps_module_break() -> None:
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
    merged, _ = merge_undersized_chapters(chapters, min_sections=2, min_chars=400)
    assert len(merged) == 2

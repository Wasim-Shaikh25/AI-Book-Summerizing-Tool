"""Tests for DOCX TOC export planning."""
from __future__ import annotations

from src.modules.export.docx_notes_exporter import _collect_chapter_export_plan


def test_collect_export_plan_builds_toc_before_chapters() -> None:
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Intro",
                "sections": [
                    {"section_id": "S1", "heading": "One"},
                    {"section_id": "S2", "heading": "Two"},
                ],
            },
            {
                "chapter_id": "C2",
                "heading": "Next",
                "sections": [{"section_id": "S3", "heading": "Three"}],
            },
        ]
    }
    rewritten = {"S1": "body one", "S2": "body two", "S3": "body three"}

    toc_rows, chapter_blocks = _collect_chapter_export_plan(
        hierarchy,
        rewritten,
        bundle_size=1,
        bundle_export=False,
        compact_toc=False,
    )

    assert len(chapter_blocks) == 2
    assert toc_rows[0][1] == "Intro"
    assert toc_rows[1][1] == "One"
    assert toc_rows[-1][1] == "Three"
    assert chapter_blocks[0]["bookmark"].startswith("ch_")

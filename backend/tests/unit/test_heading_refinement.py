"""Tests for stage 15i heading refinement (chapters, sections, subheadings)."""

from __future__ import annotations

from src.modules.structure.final_structuring.subheading_refinement import (
    _dedupe_subheadings,
    refine_chapter_titles,
    run_heading_refinement,
)


def test_dedupe_subheadings_keeps_richest() -> None:
    subs = [
        {"heading": "Quran", "fragment": {"chars": 10}},
        {"heading": "Quran", "fragment": {"chars": 200}},
    ]
    removed = _dedupe_subheadings(subs)
    assert removed == 1
    assert len(subs) == 1
    assert subs[0]["fragment"]["chars"] == 200


def test_refine_chapter_title_not_first_section_only() -> None:
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "A. Hanafi School",
                "sections": [
                    {"section_id": "S1", "heading": "A. Hanafi School", "page_number": 7},
                    {"section_id": "S2", "heading": "D. Hanbali School", "page_number": 7},
                    {"section_id": "S3", "heading": "Meaning of mahr", "page_number": 7},
                    {"section_id": "S4", "heading": "Registration", "page_number": 8},
                ],
            }
        ]
    }
    changed = refine_chapter_titles(hierarchy)
    assert changed >= 1
    assert hierarchy["chapters"][0]["heading"] != "A. Hanafi School"


def test_run_heading_refinement_sets_meta() -> None:
    hierarchy = {
        "meta": {"total_sections": 2},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Intro",
                "sections": [
                    {
                        "section_id": "S1",
                        "heading": "Topic",
                        "subheadings": [{"heading": "Sub A", "fragment": {"chars": 50, "preview": "text"}}],
                    }
                ],
            }
        ],
    }
    out = run_heading_refinement(hierarchy)
    assert out["meta"].get("heading_refinement_method")
    assert "heading_refinement_section_titles" in out["meta"]

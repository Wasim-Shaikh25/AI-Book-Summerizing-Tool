"""Tests for stage 15h universal chapter placement (no book-specific aliases)."""

from __future__ import annotations

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.final_structuring.chapter_placement import (
    infer_chapter_title_from_sections,
    is_structural_chapter_break,
    rebalance_sections_by_page_order,
    refine_broad_chapter_titles,
    run_chapter_placement,
    section_starts_new_part,
    split_chapters_at_structural_markers,
    split_oversized_chapters,
    universal_clean_heading,
)
from src.modules.structure.final_structuring.heading_cleanup import (
    _strip_page_disambiguation_suffixes,
    sanitize_merged_section_titles,
)


def test_module_is_structural_chapter_break() -> None:
    assert is_structural_chapter_break("MODULE 2")
    assert is_structural_chapter_break("Unit 3")
    assert is_structural_chapter_break("CHAPTER I: PRELIMINARY")
    assert not is_structural_chapter_break("Section 106: Causing death by negligence.")


def test_split_at_module_boundary() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Family Law I",
            "sections": [
                {"section_id": "S1", "heading": "Intro", "page_number": 1},
                {"section_id": "S2", "heading": "MODULE 2", "page_number": 65},
                {"section_id": "S3", "heading": "Succession", "page_number": 66},
            ],
        }
    ]
    out, extra = split_chapters_at_structural_markers(chapters)
    assert extra == 1
    assert len(out) == 2
    assert out[1]["sections"][0]["heading"] == "MODULE 2"


def test_universal_clean_heading_strips_bullet() -> None:
    out = universal_clean_heading("• Absence of Proper Witness", use_transformers=False)
    assert not out.startswith("•")
    assert "Witness" in out


def test_universal_clean_heading_weak_uses_subheading_not_alias() -> None:
    out = universal_clean_heading(
        "Major",
        subheadings=[{"heading": "Competency of Parties"}],
        use_transformers=False,
    )
    assert out == "Competency of Parties"
    assert not is_weak_section_heading(out)


def test_no_hardcoded_khula_alias() -> None:
    """Khula without subheadings should not map to a fixed string from a removed alias table."""
    out = universal_clean_heading("Khula", use_transformers=False)
    assert out == "Khula"


def test_strip_page_disambiguation_suffixes() -> None:
    raw = "1. Khula — Course Part A (p. 38) — Course Part A (p. 38)"
    out = universal_clean_heading(raw, use_transformers=False)
    assert "(p." not in out
    assert out.lower().startswith("khula")

    raw2 = "2. Actual possession: — Part I (p. 33) — Part I (p. 33)"
    out2 = _strip_page_disambiguation_suffixes(raw2)
    assert "(p." not in out2
    assert "actual possession" in out2.lower()


def test_section_starts_new_part_from_subheading() -> None:
    sec = {
        "heading": "Succession overview",
        "subheadings": [{"heading": "MODULE 3"}],
    }
    assert section_starts_new_part(sec)


def test_rebalance_moves_early_page_section() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Intro",
            "sections": [
                {"section_id": "S1", "heading": "Overview", "page_number": 1},
            ],
        },
        {
            "chapter_id": "C2",
            "heading": "Later topic",
            "sections": [
                {"section_id": "S2", "heading": "Parentage", "page_number": 51},
                {"section_id": "S3", "heading": "Syllabus", "page_number": 1},
            ],
        },
    ]
    moved = rebalance_sections_by_page_order(chapters)
    assert moved >= 1
    c1_ids = {s["section_id"] for s in chapters[0]["sections"]}
    assert "S3" in c1_ids


def test_split_oversized_chapter() -> None:
    sections = [
        {"section_id": f"S{i}", "heading": f"Topic {i}", "page_number": i * 2}
        for i in range(1, 16)
    ]
    sections[8] = {
        "section_id": "S9",
        "heading": "MODULE 2",
        "page_number": 20,
        "subheadings": [],
    }
    chapters = [{"chapter_id": "C1", "heading": "Big", "sections": sections}]
    out, extra = split_oversized_chapters(chapters)
    assert extra >= 1
    assert len(out) >= 2


def test_run_chapter_placement_updates_chapter_count() -> None:
    hierarchy = {
        "meta": {"total_chapters": 2, "total_sections": 4},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Part A",
                "sections": [
                    {"section_id": "S1", "heading": "Intro", "page_number": 1},
                    {"section_id": "S2", "heading": "MODULE 2", "page_number": 40},
                    {"section_id": "S3", "heading": "Topic", "page_number": 41},
                ],
            }
        ],
    }
    out = run_chapter_placement(hierarchy)
    assert out["meta"]["total_chapters"] == len(out["chapters"])
    assert len(out["chapters"]) >= 2


def test_infer_chapter_title_not_first_section_only() -> None:
    sections = [
        {"section_id": "S1", "heading": "A. Hanafi School", "page_number": 7},
        {"section_id": "S2", "heading": "D. Hanbali School", "page_number": 7},
        {"section_id": "S3", "heading": "Meaning of mahr", "page_number": 7},
        {"section_id": "S4", "heading": "Registration", "page_number": 8},
    ]
    title = infer_chapter_title_from_sections(sections)
    assert title != "A. Hanafi School"
    assert len(title) >= 8


def test_refine_broad_chapter_titles_renames_narrow_parent() -> None:
    chapters = [
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
    changed = refine_broad_chapter_titles(chapters)
    assert changed >= 1
    assert chapters[0]["heading"] != "A. Hanafi School"


def test_sanitize_merged_section_titles() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Part I",
            "sections": [
                {
                    "section_id": "S1",
                    "heading": "Right of retention — Part I (p. 33) — Part I (p. 33)",
                }
            ],
        }
    ]
    changed = sanitize_merged_section_titles(chapters)
    assert changed >= 1
    assert "(p." not in chapters[0]["sections"][0]["heading"]

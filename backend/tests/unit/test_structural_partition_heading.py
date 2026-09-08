"""Tests for structural partition heading detection (CHAPTER I:, OF OFFENCES…)."""

from __future__ import annotations

from src.modules.structure.dropped_heading_registry import (
    is_acceptable_study_title,
    is_structural_partition_heading,
    partition_heading_to_study_title,
)
from src.modules.structure.final_structuring.chapter_placement import is_structural_chapter_break
from src.modules.structure.final_structuring.heading_title_engine import (
    resolve_chapter_display_heading,
    resolve_section_display_heading,
)


def test_structural_partition_headings_detected() -> None:
    samples = [
        "CHAPTER I: PRELIMINARY",
        "CHAPTER XII: OF OFFENCES BY OR RELATING TO PUBLIC SERVANTS",
        "CHAPTER VII: OF OFFENCES AGAINST THE STATE",
        "OF KIDNAPPING, ABDUCTION, SLAVERY AND FORCED LABOUR",
        "CHAPTER II – OF PUNISHMENTS",
        "PART III",
    ]
    for title in samples:
        assert is_structural_partition_heading(title), title
        assert is_structural_chapter_break(title), title
        assert not is_acceptable_study_title(title), title


def test_partition_heading_to_study_title() -> None:
    assert partition_heading_to_study_title("CHAPTER I: PRELIMINARY") == "Preliminary"
    assert "Offences" in partition_heading_to_study_title("OF OFFENCES AGAINST THE STATE")
    assert partition_heading_to_study_title("Section 106: Causing death by negligence.") == (
        "Section 106: Causing death by negligence."
    )


def test_section_display_rejects_chapter_line() -> None:
    sec = {
        "heading": "CHAPTER I: PRELIMINARY",
        "subheadings": [{"heading": "General explanations"}],
        "fragment": {"preview": "This Act may be called the Bharatiya Nyaya Sanhita"},
        "page_number": 3,
    }
    out = resolve_section_display_heading(sec, chapter_heading="Preliminary", use_transformers=False)
    assert "CHAPTER I" not in out
    assert out


def test_chapter_display_normalizes_partition() -> None:
    ch = {
        "heading": "CHAPTER I: PRELIMINARY",
        "sections": [
            {
                "section_id": "S1",
                "heading": "General explanations",
                "subheadings": [],
                "fragment": {},
            }
        ],
    }
    out = resolve_chapter_display_heading(ch, use_transformers=False)
    assert out == "Preliminary"

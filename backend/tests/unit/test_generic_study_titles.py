"""Tests for generic title detection and semantic refinement."""

from __future__ import annotations

from src.modules.structure.dropped_heading_registry import (
    is_acceptable_study_title,
    is_generic_study_title,
    is_noisy_fragment_heading,
)
from src.modules.structure.final_structuring.hierarchy_openai_refinement import (
    _refine_semantic_titles,
)


def test_generic_module_and_overview_titles() -> None:
    # Structural generic patterns only — no subject-specific vocabulary.
    assert is_generic_study_title("Overview of Contracts")
    assert is_generic_study_title("Photosynthesis Overview")
    assert is_generic_study_title("MODULE 4:")
    assert is_generic_study_title("GENERAL PRINCIPLES")
    assert is_generic_study_title("introduction")
    assert not is_generic_study_title("Meaning of Mahr")
    # Book-title echo is generic via the subject-agnostic book_title comparison.
    assert is_generic_study_title("Family Law I", book_title="Family Law I")


def test_noisy_fragment_headings_rejected() -> None:
    assert is_noisy_fragment_heading("(IPC")
    assert is_noisy_fragment_heading("A)")
    assert is_noisy_fragment_heading("10 years")
    assert not is_noisy_fragment_heading("Section 302 IPC — Murder")
    assert not is_acceptable_study_title("(IPC")


def test_refine_semantic_titles_replaces_generic_chapter() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "MODULE 1:",
            "sections": [
                {"section_id": "S1", "heading": "Meaning of mahr", "page_number": 7, "subheadings": []},
                {"section_id": "S2", "heading": "Khula", "page_number": 34, "subheadings": []},
                {"section_id": "S3", "heading": "Registration", "page_number": 8, "subheadings": []},
            ],
        }
    ]
    changed = _refine_semantic_titles(chapters, book_title="")
    assert changed >= 1
    assert chapters[0]["heading"] != "MODULE 1:"
    assert " — " in chapters[0]["heading"] or chapters[0]["heading"] in {"Khula", "Meaning of mahr", "Registration"}

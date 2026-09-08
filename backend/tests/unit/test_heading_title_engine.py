"""Tests for local-first heading title engine (rules + MiniLM)."""

from __future__ import annotations

from src.modules.structure.dropped_heading_registry import (
    is_acceptable_study_title,
    is_flan_awkward_title,
    is_outline_heading,
    topic_from_labeled_prose,
)
from src.modules.structure.final_structuring.heading_title_engine import (
    pick_chapter_title,
    pick_section_title,
)


def test_topic_from_labeled_prose_extracts_clean_topic() -> None:
    # Subject-agnostic: works across law, science, etc.
    assert topic_from_labeled_prose("Section 309: Robbery. — Fund held and administered") == "Robbery"
    assert topic_from_labeled_prose("Chapter 3: Photosynthesis. — The process by which plants") == "Photosynthesis"
    assert topic_from_labeled_prose("Section 4: Punishments (IPC – 53)") == "Punishments"
    assert topic_from_labeled_prose("GENERAL EXCEPTIONS — Of the Right of Private Defence") == "General Exceptions"


def test_topic_from_labeled_prose_rejects_pure_prose() -> None:
    # No clean topic after the label -> empty (caller falls back to preview/subheadings)
    assert topic_from_labeled_prose("Explanation: The words lawful guardian in this clause include any person") == ""


def test_acceptance_gate_rejects_statute_prose() -> None:
    assert not is_acceptable_study_title("Section 309: Robbery. — Fund held and administered")
    assert not is_acceptable_study_title("Explanation: The words lawful guardian include")
    assert is_acceptable_study_title("Robbery")


def test_pick_section_title_extracts_topic_from_statute_prose() -> None:
    section = {
        "section_id": "S1",
        "heading": "Section 309: Robbery. — Fund held and administered by the Corporation",
        "page_number": 12,
        "subheadings": [],
        "fragment": {"preview": "Robbery is theft accompanied by force or threat against a person."},
    }
    title = pick_section_title(section, chapter_heading="Offences", use_transformers=False)
    assert "Section 309" not in title
    assert "—" not in title
    assert title


def test_rejects_outline_and_flan_awkward_titles() -> None:
    assert is_outline_heading("COURSE OBJECTIVES:")
    assert is_outline_heading("Course Outcomes")
    assert is_flan_awkward_title("A Study of the Meaning of Mahr")
    assert is_flan_awkward_title("A History of Marriage")
    assert not is_acceptable_study_title("A Study of the Meaning of Mahr")
    assert is_acceptable_study_title("Meaning of mahr")


def test_pick_chapter_title_range_not_first_section() -> None:
    sections = [
        {"section_id": "S1", "heading": "A. Hanafi School", "page_number": 7},
        {"section_id": "S2", "heading": "D. Hanbali School", "page_number": 7},
        {"section_id": "S3", "heading": "Meaning of mahr", "page_number": 7},
        {"section_id": "S4", "heading": "Registration", "page_number": 8},
    ]
    title = pick_chapter_title(sections)
    assert title != "A. Hanafi School"
    assert not is_flan_awkward_title(title)
    assert " — " in title or title in {"Registration", "Meaning of mahr", "D. Hanbali School"}


def test_pick_chapter_title_pins_outline_to_book_title() -> None:
    sections = [
        {"section_id": "S1", "heading": "COURSE OBJECTIVES:", "page_number": 1},
        {"section_id": "S2", "heading": "Course Outcomes", "page_number": 1},
    ]
    title = pick_chapter_title(sections, book_title="FAMILY LAW I")
    assert title == "FAMILY LAW I"


def test_pick_section_title_avoids_flan_summarize_pattern() -> None:
    section = {
        "section_id": "S1",
        "heading": "C. Shaffie School",
        "page_number": 7,
        "subheadings": [
            {"heading": "Meaning of mahr", "fragment": {"preview": "Mahr is dower"}},
            {"heading": "Registration", "fragment": {"preview": "Marriage registration"}},
            {"heading": "Khula", "fragment": {"preview": "Khula divorce"}},
        ],
    }
    title = pick_section_title(section, chapter_heading="Islamic law", use_transformers=False)
    assert not is_flan_awkward_title(title)
    assert "Study of" not in title


def test_ensure_study_safe_heading_repairs_weak_fragment() -> None:
    from src.modules.quality.heuristics import classify_heading
    from src.modules.structure.final_structuring.heading_title_engine import ensure_study_safe_heading

    repaired = ensure_study_safe_heading(
        "Section topic (p. 32)",
        chapter_heading="General Exceptions",
        page_number=32,
    )
    assert classify_heading(repaired) == "looks_ok"

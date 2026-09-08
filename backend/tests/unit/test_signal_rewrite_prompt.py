"""Tests for signal_rewrite.hierarchy_prompt + inner_heading_decider."""

from __future__ import annotations

from src.modules.generation.signal_rewrite.hierarchy_prompt import (
    build_signal_section_prompt,
    build_signal_system_prompt,
)
from src.modules.generation.signal_rewrite.inner_heading_decider import (
    validate_inner_headings,
)


def test_system_prompt_contains_universal_rules_and_user_instruction() -> None:
    sp = build_signal_system_prompt(user_instruction="short and exam-ready")
    assert "exporter" in sp.lower()
    assert "###" in sp
    assert "short and exam-ready" in sp


def test_system_prompt_falls_back_when_no_user_instruction() -> None:
    sp = build_signal_system_prompt(user_instruction="")
    assert "Rewrite the source into clear study notes." in sp


def test_section_prompt_carries_chapter_and_inner_heading_hints() -> None:
    user = build_signal_section_prompt(
        book_title="Sample Book",
        chapter_number=2,
        chapter_heading="CHAPTER 2: Negligence",
        section_number=4,
        section_heading="Standard of Care",
        section_page_start=15,
        section_page_end=18,
        source_text="Source text that the LLM must use only.",
        inner_headings=[
            {
                "text": "Reasonable Man Test",
                "line_id": 102,
                "page_number": 16,
                "confidence": 0.82,
                "signals_used": ["bold", "centered"],
            }
        ],
        prev_section_heading="Duty of Care",
        prev_section_tail="prev tail body content for continuity.",
        next_section_heading="Breach",
        next_section_head="next head body content.",
        overlap_chars=200,
    )
    assert "CHAPTER 2: Negligence" in user
    assert "Standard of Care" in user
    assert "pages 15-18" in user
    assert "Reasonable Man Test" in user
    assert "line 102" in user
    assert "Duty of Care" in user
    assert "Breach" in user
    assert "Source text that the LLM must use only." in user
    # Does NOT instruct the model to print the section title.
    assert "DO NOT change or print" in user


def test_validate_inner_headings_keeps_declared_inner_h3() -> None:
    text = "Intro paragraph.\n\n### Reasonable Man Test\nSome body."
    inner = [{"text": "Reasonable Man Test"}]
    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading="Standard of Care",
        inner_headings=inner,
    )
    assert "### Reasonable Man Test" in cleaned
    assert report.inner_accepted == 1
    assert report.inner_downgraded == 0


def test_validate_inner_headings_downgrades_undeclared_h3() -> None:
    text = "Intro.\n\n### Invented Heading\nBody."
    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading="Section",
        inner_headings=[{"text": "Reasonable Man Test"}],
    )
    assert "### Invented Heading" not in cleaned
    assert "**Invented Heading**" in cleaned
    assert report.inner_downgraded == 1


def test_validate_strips_echoed_top_title() -> None:
    text = "## Standard of Care\n\nBody starts here."
    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading="Standard of Care",
        inner_headings=[],
    )
    assert not cleaned.startswith("## Standard of Care")
    assert "Body starts here." in cleaned
    assert report.top_level_stripped == 1


def test_validate_keeps_unrelated_top_heading() -> None:
    text = "## Unrelated Heading\n\nBody."
    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading="Standard of Care",
        inner_headings=[],
    )
    assert "## Unrelated Heading" in cleaned
    assert report.top_level_stripped == 0


def test_validate_unwraps_outer_code_fence() -> None:
    text = "```\nBody line 1.\n\n### Real Sub\nMore.\n```"
    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading="Section",
        inner_headings=[{"text": "Real Sub"}],
    )
    assert not cleaned.startswith("```")
    assert "Body line 1." in cleaned
    assert "### Real Sub" in cleaned
    assert report.fence_unwrapped


def test_validate_keeps_mermaid_fence() -> None:
    text = "Body.\n\n```mermaid\ngraph TD; A-->B;\n```"
    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading="Section",
        inner_headings=[],
    )
    assert "```mermaid" in cleaned
    assert not report.fence_unwrapped


def test_validate_handles_empty_output() -> None:
    cleaned, report = validate_inner_headings(
        generated_text="",
        section_heading="Section",
        inner_headings=[],
    )
    assert cleaned == ""
    assert "empty_output" in report.notes

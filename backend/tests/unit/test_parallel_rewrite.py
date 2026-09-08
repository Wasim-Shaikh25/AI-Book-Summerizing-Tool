"""Tests for parallel rewrite with context overlap."""
from __future__ import annotations

from src.modules.generation.parallel_rewrite import build_rewrite_jobs, rewrite_sections_parallel
from src.modules.generation.rewrite_prompts import build_section_user_prompt_with_context


def test_build_rewrite_jobs_includes_overlap() -> None:
    sections = [
        {"section_id": "S1", "heading": "Intro", "text": "A" * 1000},
        {"section_id": "S2", "heading": "Middle", "text": "B" * 1000},
        {"section_id": "S3", "heading": "End", "text": "C" * 1000},
    ]
    jobs = build_rewrite_jobs(sections, max_source_chars=500, overlap_chars=120)
    assert jobs[1].prev_heading == "Intro"
    assert len(jobs[1].prev_overlap) > 0
    assert jobs[1].next_heading == "End"
    assert len(jobs[1].next_overlap) > 0
    assert jobs[0].prev_overlap == ""
    assert jobs[2].next_overlap == ""


def test_prompt_labels_context_as_non_primary(monkeypatch) -> None:
    # Study mode emits bold-subheading "Subtopics" guidance (book mode weaves into prose).
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    prompt = build_section_user_prompt_with_context(
        user_instruction="short notes",
        heading="Middle",
        source_text="main body",
        prev_heading="Intro",
        prev_overlap="tail text",
        next_heading="End",
        next_overlap="head text",
        chapter_heading="Fundamental Rights",
        subheadings=["Art. 14", "Art. 15"],
    )
    assert "Primary source" in prompt
    assert "continuity only" in prompt
    assert "Output notes for the primary section only" in prompt
    assert "Chapter title (use as context only" in prompt
    assert "Fundamental Rights" in prompt
    assert "Art. 14" in prompt
    assert "Subtopics" in prompt
    assert "Use ### for each distinct sub-topic" in prompt


def test_parallel_rewrite_preserves_all_section_ids(monkeypatch) -> None:
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "book")
    sections = [
        {"section_id": "S1", "heading": "One", "text": "alpha"},
        {"section_id": "S2", "heading": "Two", "text": "beta"},
        {"section_id": "S3", "heading": "Three", "text": "gamma"},
    ]

    def fake_generate(system: str, user: str) -> str:
        if "Section title (use this exact label for the section topic): Two\n" in user:
            return "**Two**\n\nnotes-two"
        if "Section title (use this exact label for the section topic): One\n" in user:
            return "**One**\n\nnotes-one"
        if "Section title (use this exact label for the section topic): Three\n" in user:
            return "**Three**\n\nnotes-three"
        return ""

    out = rewrite_sections_parallel(
        sections,
        user_instruction="test",
        system="sys",
        generate=fake_generate,
        workers=3,
        overlap_chars=10,
    )
    assert set(out.keys()) == {"S1", "S2", "S3"}
    assert all(out.values())
    assert "Two" in out["S2"] or "two" in out["S2"].lower()

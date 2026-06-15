"""Tests for RAG context builder."""

from __future__ import annotations

from src.modules.rag.context_builder import build_qa_context, dedupe_sections


def test_dedupe_sections_by_id() -> None:
    sections = [
        {"section_id": "S1", "heading": "Tort", "text": "A"},
        {"section_id": "S1", "heading": "Tort duplicate", "text": "B"},
        {"section_id": "S2", "heading": "Negligence", "text": "C"},
    ]
    out = dedupe_sections(sections)
    assert len(out) == 2


def test_build_qa_context_citations_and_budget() -> None:
    sections = [
        {"section_id": "S1", "heading": "Definition", "chapter_heading": "Intro", "page_number": 3, "text": "X" * 500},
        {"section_id": "S2", "heading": "Duty", "text": "Y" * 500},
    ]
    context, cites = build_qa_context(sections, max_chars=800, max_section_chars=200)
    assert "[1]" in context
    assert "Definition" in context
    assert len(cites) >= 1
    assert len(context) <= 800

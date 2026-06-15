"""Tests for book Q&A retrieval."""
from __future__ import annotations

from src.modules.generation.qa_engine import _fallback_subject_relevance, retrieve_sections


def test_retrieve_sections_prefers_heading_match() -> None:
    sections = [
        {"heading": "Definition of Tort", "text": "A tort is a civil wrong..."},
        {"heading": "Contract Law Intro", "text": "Contracts require offer and acceptance..."},
    ]
    hits = retrieve_sections(sections, "What is the definition of tort?", top_k=1)
    assert hits[0]["heading"] == "Definition of Tort"


def test_fallback_subject_relevance_uses_book_domain_tokens() -> None:
    related, reason = _fallback_subject_relevance(
        "Explain plant physiology",
        subject_hint="Botany — Plant Physiology",
        book_title="Introduction to Botany",
    )
    assert related is True
    assert "overlap" in reason.lower()


def test_fallback_subject_relevance_defaults_to_related() -> None:
    related, reason = _fallback_subject_relevance(
        "What is quantum entanglement?",
        subject_hint="Introduction to Botany",
        book_title="Plant Biology 101",
    )
    assert related is True
    assert "assume related" in reason.lower() or "uploaded book" in reason.lower()

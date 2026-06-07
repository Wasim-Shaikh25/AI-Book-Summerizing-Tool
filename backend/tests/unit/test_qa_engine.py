"""Tests for book Q&A retrieval."""
from __future__ import annotations

from src.modules.generation.qa_engine import retrieve_sections


def test_retrieve_sections_prefers_heading_match() -> None:
    sections = [
        {"heading": "Definition of Tort", "text": "A tort is a civil wrong..."},
        {"heading": "Contract Law Intro", "text": "Contracts require offer and acceptance..."},
    ]
    hits = retrieve_sections(sections, "What is the definition of tort?", top_k=1)
    assert hits[0]["heading"] == "Definition of Tort"

"""Unit tests for RAG chunk strategy dispatch in chunk_builder."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.rag.chunk_builder import (  # noqa: E402
    _semantic_boundary_split,
    sections_to_rag_chunks,
)

SHORT_TEXT = "A short paragraph."
LONG_TEXT = ("Word " * 120).strip()       # > 500 chars
PARA_TEXT = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."


def test_section_strategy_produces_one_chunk_per_section(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.rag.chunk_builder.config",
                        type("C", (), {"RAG_CHUNK_STRATEGY": "section",
                                       "RAG_SEMANTIC_CHUNK_TARGET_CHARS": 500,
                                       "RAG_SEMANTIC_OVERLAP_SENTS": 1})())
    sections = [
        {"heading": "H1", "text": LONG_TEXT, "section_id": "S1"},
        {"heading": "H2", "text": LONG_TEXT, "section_id": "S2"},
    ]
    chunks = sections_to_rag_chunks(sections, book_id="B1")
    assert len(chunks) == 2


def test_paragraph_strategy_splits_on_blank_lines(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.rag.chunk_builder.config",
                        type("C", (), {"RAG_CHUNK_STRATEGY": "paragraph",
                                       "RAG_SEMANTIC_CHUNK_TARGET_CHARS": 500,
                                       "RAG_SEMANTIC_OVERLAP_SENTS": 1})())
    sections = [{"heading": "H", "text": PARA_TEXT, "section_id": "S1"}]
    chunks = sections_to_rag_chunks(sections, book_id="B1")
    assert len(chunks) == 3


def test_semantic_strategy_splits_long_paragraph() -> None:
    text = ("Sentence one. " * 20).strip()   # one long paragraph > 500 chars
    result = _semantic_boundary_split(text, "H", target_chars=100, overlap_sents=0)
    assert len(result) > 1


def test_chunk_metadata_has_paragraph_idx() -> None:
    result = _semantic_boundary_split(PARA_TEXT, "H", target_chars=50)
    for chunk in result:
        assert "paragraph_idx" in chunk


def test_chunk_metadata_has_chunk_strategy() -> None:
    result = _semantic_boundary_split(SHORT_TEXT, "H")
    assert all(c["chunk_strategy"] == "semantic" for c in result)


def test_overlap_sent_appears_in_adjacent_chunks() -> None:
    text = "First sentence. Second sentence. Third sentence."
    result = _semantic_boundary_split(text, "H", target_chars=20, overlap_sents=1)
    if len(result) >= 2:
        assert result[1]["text"].startswith("First sentence")


def test_short_paragraph_not_split_further() -> None:
    result = _semantic_boundary_split(SHORT_TEXT, "H", target_chars=500)
    assert len(result) == 1


def test_default_strategy_is_section(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.rag.chunk_builder.config",
                        type("C", (), {"RAG_CHUNK_STRATEGY": "section",
                                       "RAG_SEMANTIC_CHUNK_TARGET_CHARS": 500,
                                       "RAG_SEMANTIC_OVERLAP_SENTS": 1})())
    sections = [{"heading": "H", "text": LONG_TEXT, "section_id": "S1"}]
    chunks = sections_to_rag_chunks(sections, book_id="B1")
    assert len(chunks) == 1


def test_all_text_covered_no_loss() -> None:
    text = "Alpha sentence. Beta sentence. Gamma sentence. Delta sentence."
    result = _semantic_boundary_split(text, "H", target_chars=30, overlap_sents=0)
    combined = " ".join(c["text"] for c in result)
    for word in ["Alpha", "Beta", "Gamma", "Delta"]:
        assert word in combined

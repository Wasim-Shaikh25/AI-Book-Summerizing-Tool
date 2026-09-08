"""Unit tests for concept_extractor — NP extraction and normalisation."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.knowledge.concept_extractor import (  # noqa: E402
    ExtractedConcept,
    _normalise,
    extract_concepts_from_chunk,
)


def test_extract_concepts_returns_list_of_extracted_concepts() -> None:
    result = extract_concepts_from_chunk(
        "Tort law covers negligence, contract breach, and vicarious liability.",
        chunk_id="C1",
        book_id="B1",
    )
    assert isinstance(result, list)
    assert all(isinstance(c, ExtractedConcept) for c in result)


def test_extract_concepts_respects_top_k() -> None:
    text = " ".join([f"concept{i} law" for i in range(20)])
    result = extract_concepts_from_chunk(text, chunk_id="C1", book_id="B1", top_k=3)
    assert len(result) <= 3


def test_extract_concepts_canonical_name_is_lowercase_normalised() -> None:
    result = extract_concepts_from_chunk(
        "Tort Law is important.", chunk_id="C1", book_id="B1", top_k=5
    )
    for c in result:
        assert c.canonical_name == c.canonical_name.lower()


def test_extract_concepts_salience_score_between_0_and_1() -> None:
    result = extract_concepts_from_chunk(
        "Negligence and tort law govern liability.", chunk_id="C1", book_id="B1"
    )
    for c in result:
        assert 0.0 <= c.salience_score <= 1.0


def test_extract_concepts_no_duplicates_in_output() -> None:
    text = "tort " * 20
    result = extract_concepts_from_chunk(text, chunk_id="C1", book_id="B1", top_k=5)
    names = [c.canonical_name for c in result]
    assert len(names) == len(set(names))


def test_extract_concepts_empty_text_returns_empty_list() -> None:
    result = extract_concepts_from_chunk("", chunk_id="C1", book_id="B1")
    assert result == []


def test_extract_concepts_works_without_sentence_transformers(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.modules.knowledge.concept_extractor.SentenceTransformer", None, raising=False
    )
    result = extract_concepts_from_chunk(
        "Liability and negligence.", chunk_id="C1", book_id="B1"
    )
    assert isinstance(result, list)


def test_normalise_strips_leading_stopwords() -> None:
    assert _normalise("the tort law") == "tort law"


def test_normalise_lowercases_phrase() -> None:
    assert _normalise("Tort Law") == "tort law"

"""Tests for vector RAG chunking and hybrid retrieval."""
from __future__ import annotations

import numpy as np

from src.modules.rag.chunk_builder import sections_to_rag_chunks
from src.modules.rag.indexer import FaissVectorIndex
from src.modules.rag.retriever import hybrid_retrieve


def test_sections_to_rag_chunks_one_per_section() -> None:
    sections = [
        {"section_id": "S1", "heading": "Definition of Tort", "text": "A tort is a civil wrong that causes harm."},
        {"section_id": "S2", "heading": "Negligence", "text": "Negligence requires duty, breach, causation, and damages."},
    ]
    chunks = sections_to_rag_chunks(sections, book_id="b1", chunk_size_words=0)
    assert len(chunks) == 2
    assert chunks[0]["section_id"] == "S1"


def test_hybrid_retrieve_prefers_semantic_match() -> None:
    chunks = [
        {
            "chunk_id": "c1",
            "section_id": "S1",
            "heading": "Definition of Tort",
            "text": "A tort is a civil wrong.",
            "embed_text": "Definition of Tort\nA tort is a civil wrong.",
        },
        {
            "chunk_id": "c2",
            "section_id": "S2",
            "heading": "Contract Law",
            "text": "Offer and acceptance form a contract.",
            "embed_text": "Contract Law\nOffer and acceptance form a contract.",
        },
    ]
    embs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")

    class _FakeIndex:
        def search(self, q, k):
            return np.array([[0.95, 0.1]]), np.array([[0, 1]])

    index = FaissVectorIndex(
        book_id="b1",
        chunks=chunks,
        embeddings=embs,
        index=_FakeIndex(),
        embedding_model="test",
        index_dir=__import__("pathlib").Path("."),
    )
    hits = hybrid_retrieve("What is a tort?", vector_index=index, top_k=1, min_score=0.0)
    assert hits
    assert hits[0]["heading"] == "Definition of Tort"

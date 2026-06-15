"""Tests for RAG cross-encoder reranker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.modules.rag.reranker import rerank_chunks


@patch("src.modules.rag.reranker.get_rag_reranker")
def test_rerank_chunks_orders_by_score(mock_get) -> None:
    reranker = MagicMock()
    mock_get.return_value = reranker
    reranker.score_pairs.return_value = [0.2, 0.9]

    chunks = [
        {"chunk_id": "c1", "heading": "Contract", "text": "offer acceptance"},
        {"chunk_id": "c2", "heading": "Tort", "text": "negligence duty breach"},
    ]
    out = rerank_chunks("What is negligence?", chunks, top_k=1)
    assert len(out) == 1
    assert out[0]["heading"] == "Tort"
    assert out[0]["_rerank_score"] == 0.9

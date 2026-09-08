"""Unit tests for corpus_builder — multi-book index lifecycle."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.rag.corpus_builder import (  # noqa: E402
    build_corpus_index,
    invalidate_corpus_index,
    load_corpus_index,
)

_MOCK_CHUNKS_A = [{"chunk_id": "A:001", "text": "chunk a one", "source_book_id": "A"}]
_MOCK_CHUNKS_B = [{"chunk_id": "B:001", "text": "chunk b one", "source_book_id": "B"}]


def _mock_repo(chunks_by_book: dict) -> MagicMock:
    repo = MagicMock()
    repo.get_chunks.side_effect = lambda book_id: chunks_by_book.get(book_id, [])
    return repo


def test_load_corpus_index_returns_none_when_not_built(tmp_path: Path) -> None:
    result = load_corpus_index("user1", data_dir=tmp_path)
    assert result is None


def test_invalidate_deletes_corpus_files(tmp_path: Path) -> None:
    cdir = tmp_path / "corpus_user1"
    cdir.mkdir()
    (cdir / "corpus_chunks.json").write_text("[]")
    invalidate_corpus_index("user1", data_dir=tmp_path)
    assert not cdir.exists()


def test_corpus_chunk_has_book_id_metadata(tmp_path: Path) -> None:
    repo = _mock_repo({"A": _MOCK_CHUNKS_A})
    with patch("src.modules.rag.corpus_builder.build_faiss_index") as mock_build:
        mock_build.return_value = MagicMock(chunk_count=1)
        build_corpus_index(["A"], "user1", data_dir=tmp_path, rag_repo=repo)

    chunks_file = tmp_path / "corpus_user1" / "corpus_chunks.json"
    chunks = json.loads(chunks_file.read_text())
    assert all("source_book_id" in c for c in chunks)


def test_build_corpus_index_aggregates_chunks_from_multiple_books(tmp_path: Path) -> None:
    repo = _mock_repo({"A": _MOCK_CHUNKS_A, "B": _MOCK_CHUNKS_B})
    with patch("src.modules.rag.corpus_builder.build_faiss_index") as mock_build:
        mock_build.return_value = MagicMock(chunk_count=2)
        build_corpus_index(["A", "B"], "user1", data_dir=tmp_path, rag_repo=repo)

    chunks_file = tmp_path / "corpus_user1" / "corpus_chunks.json"
    chunks = json.loads(chunks_file.read_text())
    assert len(chunks) == 2


def test_retrieve_cross_book_returns_empty_when_disabled(monkeypatch) -> None:
    from src.modules.rag.service import RagService

    monkeypatch.setattr(
        "src.modules.rag.service.config",
        type("C", (), {"RAG_CORPUS_INDEX_ENABLED": False})(),
    )
    svc = RagService.__new__(RagService)
    result = svc.retrieve_cross_book("query", "user1")
    assert result == []

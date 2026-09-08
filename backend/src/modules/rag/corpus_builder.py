"""Build and manage a corpus-level FAISS index across all books for a user.

Cross-book index is built lazily on first call to ``build_corpus_index`` and
stored under ``data_dir/corpus_{user_id}/``.  Call ``invalidate_corpus_index``
whenever a book is added or removed.

Activated by RAG_CORPUS_INDEX_ENABLED=1 (default 0).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

logger = logging.getLogger(__name__)

try:
    from src.modules.rag.indexer import build_faiss_index, load_faiss_index  # noqa: F401
except Exception:  # pragma: no cover — available at runtime; missing in isolated test context
    build_faiss_index = None  # type: ignore[assignment]
    load_faiss_index = None   # type: ignore[assignment]

_CORPUS_FAISS = "corpus.faiss"
_CORPUS_CHUNKS = "corpus_chunks.json"


class CorpusIndex(NamedTuple):
    index: Any
    chunk_count: int
    user_id: str


def _corpus_dir(user_id: str, data_dir: Path) -> Path:
    return data_dir / f"corpus_{user_id}"


def build_corpus_index(
    book_ids: List[str],
    user_id: str,
    *,
    data_dir: Path,
    rag_repo: Any,
    embedding_model: str = "all-MiniLM-L6-v2",
) -> Any:
    """Aggregate per-book chunk files into a single FAISS corpus index.

    Stored at: ``data_dir/corpus_{user_id}/corpus.faiss`` + ``corpus_chunks.json``.
    Each chunk gets ``source_book_id`` metadata added.

    Args:
        book_ids:        List of book IDs to include.
        user_id:         Owner user ID (used for path namespacing).
        data_dir:        Root directory for RAG indexes.
        rag_repo:        RagRepository instance — must support ``get_chunks(book_id)``.
        embedding_model: SentenceTransformer model name.

    Returns:
        FAISS index object returned by ``build_faiss_index``.
    """
    _build_fn = build_faiss_index
    if _build_fn is None:  # pragma: no cover
        from src.modules.rag.indexer import build_faiss_index as _build_fn  # type: ignore[assignment]

    all_chunks: List[Dict[str, Any]] = []
    for book_id in book_ids:
        chunks = rag_repo.get_chunks(book_id) or []
        for c in chunks:
            c = dict(c)
            c["source_book_id"] = book_id
            all_chunks.append(c)

    if not all_chunks:
        raise ValueError("No chunks found for any book_id in corpus build")

    cdir = _corpus_dir(user_id, data_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / _CORPUS_CHUNKS).write_text(
        json.dumps(all_chunks, ensure_ascii=False), encoding="utf-8"
    )

    index = _build_fn(
        book_id=f"corpus_{user_id}",
        chunks=all_chunks,
        index_dir=cdir.parent,
        embedding_model=embedding_model,
    )
    logger.info(
        "Corpus index built: user=%s books=%d chunks=%d",
        user_id,
        len(book_ids),
        len(all_chunks),
    )
    return index


def load_corpus_index(user_id: str, *, data_dir: Path) -> Optional[Any]:
    """Load existing corpus index or return None if not built."""
    _load_fn = load_faiss_index
    if _load_fn is None:  # pragma: no cover
        from src.modules.rag.indexer import load_faiss_index as _load_fn  # type: ignore[assignment]

    cdir = _corpus_dir(user_id, data_dir)
    if not (cdir / _CORPUS_CHUNKS).exists():
        return None
    return _load_fn(book_id=f"corpus_{user_id}", index_dir=cdir.parent)


def invalidate_corpus_index(user_id: str, *, data_dir: Path) -> None:
    """Delete corpus index files — call when a book is added or removed."""
    import shutil

    cdir = _corpus_dir(user_id, data_dir)
    if cdir.exists():
        shutil.rmtree(cdir)
        logger.info("Corpus index invalidated for user=%s", user_id)

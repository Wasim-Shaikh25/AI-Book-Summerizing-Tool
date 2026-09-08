"""RAG service — index lifecycle + retrieval API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src import config
from src.modules.rag.chunk_builder import sections_to_rag_chunks
from src.modules.rag.indexer import FaissVectorIndex, build_faiss_index, load_faiss_index
from src.modules.rag.retriever import chunks_to_sections, hybrid_retrieve
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.rag_repository import RagRepository

logger = logging.getLogger(__name__)

_INDEX_CACHE: Dict[str, FaissVectorIndex] = {}


class RagService:
    """Build, persist, and query vector RAG indexes per book."""

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self.store = store or KnowledgeStore()
        self.repo = RagRepository(self.store)
        self.index_dir = Path(getattr(config, "RAG_INDEX_DIR", config.OUTPUT_FOLDER + "/rag_index"))

    def ensure_index(
        self,
        *,
        book_id: str,
        sections: Sequence[Dict[str, Any]],
        force_rebuild: bool = False,
    ) -> FaissVectorIndex:
        if not force_rebuild and book_id in _INDEX_CACHE:
            return _INDEX_CACHE[book_id]

        if not force_rebuild:
            loaded = load_faiss_index(book_id=book_id, index_dir=self.index_dir)
            meta = self.repo.get_index_meta(book_id)
            if loaded and meta and int(meta.get("chunk_count") or 0) == loaded.chunk_count:
                _INDEX_CACHE[book_id] = loaded
                return loaded

        chunks = sections_to_rag_chunks(
            sections,
            book_id=book_id,
            chunk_size_words=int(getattr(config, "RAG_CHUNK_SIZE_WORDS", 0) or 0),
            chunk_overlap_words=int(getattr(config, "RAG_CHUNK_OVERLAP_WORDS", 0) or 0),
            min_chars=int(getattr(config, "RAG_MIN_CHUNK_CHARS", 40) or 40),
        )
        if not chunks:
            raise ValueError(f"No indexable chunks for book_id={book_id}")

        index = build_faiss_index(
            book_id=book_id,
            chunks=chunks,
            index_dir=self.index_dir,
            embedding_model=str(getattr(config, "RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")),
        )
        self.repo.save_chunks(book_id, chunks)
        self.repo.save_index_meta(
            book_id,
            {
                "embedding_model": index.embedding_model,
                "chunk_count": index.chunk_count,
                "index_path": str(self.index_dir / book_id / "index.faiss"),
            },
        )
        _INDEX_CACHE[book_id] = index
        logger.info("RAG index ready for book_id=%s chunks=%d", book_id, index.chunk_count)
        return index

    def retrieve(
        self,
        query: str,
        *,
        book_id: str,
        sections: Sequence[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not getattr(config, "RAG_ENABLED", True):
            from src.modules.generation.qa_engine import retrieve_sections

            return retrieve_sections(sections, query, top_k=top_k or 6)

        index = self.ensure_index(book_id=book_id, sections=sections)
        k = top_k or int(getattr(config, "RAG_TOP_K", 6) or 6)
        chunks = hybrid_retrieve(
            query,
            vector_index=index,
            top_k=k,
            vector_weight=float(getattr(config, "RAG_VECTOR_WEIGHT", 0.65)),
            lexical_weight=float(getattr(config, "RAG_LEXICAL_WEIGHT", 0.35)),
            min_score=float(getattr(config, "RAG_MIN_SCORE", 0.15)),
            rerank=bool(getattr(config, "RAG_RERANK_ENABLED", True)),
            rerank_candidates=int(getattr(config, "RAG_RERANK_CANDIDATES", 50) or 50),
            rerank_model=str(
                getattr(config, "RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
            ),
        )
        return chunks_to_sections(chunks)

    def retrieve_cross_book(
        self,
        query: str,
        user_id: str,
        *,
        book_ids: list[str] | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Retrieve from the corpus-level index spanning all books for a user.

        Builds the index lazily on first call.
        Returns [] when RAG_CORPUS_INDEX_ENABLED=0 (default).

        Args:
            query:    Natural language query.
            user_id:  Owner identifier for corpus namespacing.
            book_ids: Optional filter — restrict results to these book IDs.
            top_k:    Number of results to return.
        """
        if not getattr(config, "RAG_CORPUS_INDEX_ENABLED", False):
            return []

        from src.modules.rag.corpus_builder import build_corpus_index, load_corpus_index

        index = load_corpus_index(user_id, data_dir=self.index_dir)
        if index is None:
            all_book_ids = book_ids or list(self.repo.list_book_ids(user_id) or [])
            index = build_corpus_index(
                all_book_ids,
                user_id,
                data_dir=self.index_dir,
                rag_repo=self.repo,
                embedding_model=str(getattr(config, "RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")),
            )

        chunks = hybrid_retrieve(query, vector_index=index, top_k=top_k)

        if book_ids:
            chunks = [c for c in chunks if c.get("source_book_id") in book_ids]

        return chunks_to_sections(chunks)

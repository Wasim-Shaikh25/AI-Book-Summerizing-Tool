"""FAISS vector index build/load for RAG chunks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

logger = logging.getLogger(__name__)


class FaissVectorIndex:
    """In-memory FAISS index + chunk metadata."""

    def __init__(
        self,
        *,
        book_id: str,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray,
        index,
        embedding_model: str,
        index_dir: Path,
    ) -> None:
        self.book_id = book_id
        self.chunks = chunks
        self.embeddings = embeddings
        self.index = index
        self.embedding_model = embedding_model
        self.index_dir = index_dir

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def search(self, query: str, *, top_k: int = 6) -> List[tuple[float, Dict[str, Any]]]:
        encoder = get_mini_lm_encoder()
        q_emb = encoder.encode([query.strip()])
        if q_emb is None or self.index is None:
            return []
        q = np.asarray(q_emb, dtype="float32")
        k = min(top_k, len(self.chunks))
        if k <= 0:
            return []
        scores, indices = self.index.search(q, k)
        out: List[tuple[float, Dict[str, Any]]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            out.append((float(score), self.chunks[int(idx)]))
        return out


def _index_paths(index_dir: Path, book_id: str) -> tuple[Path, Path, Path]:
    base = index_dir / book_id
    base.mkdir(parents=True, exist_ok=True)
    return base / "index.faiss", base / "chunks.json", base / "meta.json"


def build_faiss_index(
    *,
    book_id: str,
    chunks: Sequence[Dict[str, Any]],
    index_dir: str | Path,
    embedding_model: str = "all-MiniLM-L6-v2",
) -> FaissVectorIndex:
    if not chunks:
        raise ValueError("No chunks to index")

    try:
        import faiss  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("faiss-cpu is required for vector RAG. pip install faiss-cpu") from exc

    texts = [str(c.get("embed_text") or c.get("text") or "") for c in chunks]
    encoder = get_mini_lm_encoder()
    embs = encoder.encode(texts)
    if embs is None:
        raise RuntimeError("sentence-transformers unavailable — cannot build vector index")

    vectors = np.asarray(embs, dtype="float32")
    dim = int(vectors.shape[1])
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    # Build knowledge graph when enabled
    try:
        from src import config as cfg
        if getattr(cfg, "KNOWLEDGE_GRAPH_ENABLED", False):
            from src.modules.knowledge.concept_extractor import extract_concepts_from_chunk
            from src.modules.knowledge.concept_graph import build_concept_graph
            from pathlib import Path

            all_concepts = []
            for chunk in chunks:
                text = chunk.get("text") or chunk.get("embed_text") or ""
                chunk_id = chunk.get("chunk_id") or chunk.get("section_id") or ""
                bid = chunk.get("book_id", book_id)
                if text and chunk_id:
                    concepts = extract_concepts_from_chunk(text, chunk_id=chunk_id, book_id=bid, top_k=5)
                    all_concepts.extend(concepts)

            if all_concepts:
                db_path = Path(getattr(cfg, "KNOWLEDGE_DB_PATH", "output/knowledge_base.db"))
                build_concept_graph(all_concepts, db_path=db_path)
                logger.info("Built knowledge graph with %d concepts", len(all_concepts))
    except Exception as exc:
        logger.warning("Knowledge graph build failed: %s", exc)

    idx_dir = Path(index_dir)
    faiss_path, chunks_path, meta_path = _index_paths(idx_dir, book_id)
    faiss.write_index(index, str(faiss_path))
    chunks_path.write_text(json.dumps(list(chunks), ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "book_id": book_id,
                "embedding_model": embedding_model,
                "chunk_count": len(chunks),
                "dimension": dim,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Built FAISS index: %s (%d chunks)", faiss_path, len(chunks))
    return FaissVectorIndex(
        book_id=book_id,
        chunks=list(chunks),
        embeddings=vectors,
        index=index,
        embedding_model=embedding_model,
        index_dir=idx_dir,
    )


def load_faiss_index(*, book_id: str, index_dir: str | Path) -> Optional[FaissVectorIndex]:
    try:
        import faiss  # type: ignore[import-untyped]
    except ImportError:
        return None

    idx_dir = Path(index_dir)
    faiss_path, chunks_path, meta_path = _index_paths(idx_dir, book_id)
    if not faiss_path.exists() or not chunks_path.exists():
        return None
    try:
        index = faiss.read_index(str(faiss_path))
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        if not isinstance(chunks, list) or not chunks:
            return None
        return FaissVectorIndex(
            book_id=book_id,
            chunks=chunks,
            embeddings=np.empty((0, 0)),
            index=index,
            embedding_model=str(meta.get("embedding_model") or "all-MiniLM-L6-v2"),
            index_dir=idx_dir,
        )
    except Exception as exc:
        logger.warning("Failed to load FAISS index for %s: %s", book_id, exc)
        return None

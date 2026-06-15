"""Cross-encoder rerank for hybrid RAG retrieval."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_reranker: Optional["RagCrossEncoder"] = None


class RagCrossEncoder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._available: Optional[bool] = None

    def _ensure(self) -> bool:
        if self._available is False:
            return False
        if self._model is not None:
            return True
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            self._available = True
            return True
        except Exception as exc:
            logger.warning("RAG reranker unavailable (%s): %s", self.model_name, exc)
            self._available = False
            return False

    def score_pairs(self, pairs: Sequence[tuple[str, str]]) -> List[float]:
        if not pairs:
            return []
        if not self._ensure():
            return [0.0] * len(pairs)
        try:
            scores = self._model.predict(list(pairs))
            return [float(s) for s in scores]
        except Exception as exc:
            logger.debug("RAG rerank predict failed: %s", exc)
            return [0.0] * len(pairs)


def get_rag_reranker(model_name: str) -> RagCrossEncoder:
    global _reranker
    if _reranker is None or _reranker.model_name != model_name:
        _reranker = RagCrossEncoder(model_name)
    return _reranker


def rerank_chunks(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    *,
    top_k: int = 8,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> List[Dict[str, Any]]:
    """Rerank candidate chunks with a cross-encoder; fallback preserves input order."""
    if not chunks:
        return []

    reranker = get_rag_reranker(model_name)
    pairs = []
    for ch in chunks:
        heading = str(ch.get("heading") or "").strip()
        body = str(ch.get("text") or ch.get("embed_text") or "")[:1200].strip()
        passage = f"{heading}\n{body}".strip() if heading else body
        pairs.append((query, passage or heading or body))

    scores = reranker.score_pairs(pairs)
    ranked: List[tuple[float, Dict[str, Any]]] = []
    for score, ch in zip(scores, chunks):
        row = dict(ch)
        row["_rerank_score"] = round(float(score), 4)
        ranked.append((float(score), row))

    ranked.sort(key=lambda x: (-x[0], str(x[1].get("heading") or "")))

    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for _, row in ranked:
        sid = str(row.get("section_id") or row.get("chunk_id") or row.get("heading") or "")
        if sid in seen:
            continue
        seen.add(sid)
        out.append(row)
        if len(out) >= top_k:
            break
    return out

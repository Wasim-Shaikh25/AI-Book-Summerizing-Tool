"""Lazy MiniLM encoder for heading similarity (Stage 15b)."""

from __future__ import annotations

from typing import List, Optional

import numpy as np

_encoder: Optional["MiniLmEncoder"] = None


class MiniLmEncoder:
    def __init__(self) -> None:
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            self._model = False
        return self._model

    def encode(self, texts: List[str]) -> Optional[np.ndarray]:
        model = self._ensure_model()
        if not model or model is False:
            return None
        clean = [t.strip() for t in texts if (t or "").strip()]
        if not clean:
            return None
        try:
            return np.asarray(model.encode(clean, normalize_embeddings=True))
        except Exception:
            return None

    def max_similarity(self, query_emb: np.ndarray, corpus_embs: np.ndarray) -> float:
        if query_emb is None or corpus_embs is None or len(corpus_embs) == 0:
            return 0.0
        sims = np.dot(corpus_embs, query_emb)
        return float(np.max(sims))


def get_mini_lm_encoder() -> MiniLmEncoder:
    global _encoder
    if _encoder is None:
        _encoder = MiniLmEncoder()
    return _encoder

"""Optional BigBird encoder — disabled unless transformers is installed."""

from __future__ import annotations

from typing import Optional

import numpy as np

_bigbird: "BigBirdEncoder | None" = None


class BigBirdEncoder:
    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None

    def encode(self, text: str) -> Optional[np.ndarray]:
        if not (text or "").strip():
            return None
        try:
            if self._model is None:
                from transformers import AutoModel, AutoTokenizer

                name = "google/bigbird-roberta-base"
                self._tokenizer = AutoTokenizer.from_pretrained(name)
                self._model = AutoModel.from_pretrained(name)
            tokens = self._tokenizer(text[:2048], return_tensors="pt", truncation=True, max_length=512)
            out = self._model(**tokens)
            vec = out.last_hidden_state.mean(dim=1).detach().numpy()[0]
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 1e-9 else vec
        except Exception:
            return None


def get_bigbird_encoder() -> BigBirdEncoder:
    global _bigbird
    if _bigbird is None:
        _bigbird = BigBirdEncoder()
    return _bigbird

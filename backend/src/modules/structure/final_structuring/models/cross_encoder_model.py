"""Lightweight heading/body coherence scorer for Stage 15b."""

from __future__ import annotations

import re

_cross: "CrossEncoderModel | None" = None


class CrossEncoderModel:
    def score_one(self, heading: str, body: str) -> float:
        h = (heading or "").strip().lower()
        b = (body or "").strip().lower()
        if not h or not b:
            return 0.0
        h_words = set(re.findall(r"[a-z0-9]+", h))
        b_words = set(re.findall(r"[a-z0-9]+", b))
        if not h_words:
            return 0.0
        overlap = len(h_words & b_words) / max(len(h_words), 1)
        if re.search(r"chapter\s+\d+", h) and len(b) > 40:
            overlap = max(overlap, 0.55)
        return float(min(1.0, overlap))


def get_cross_encoder() -> CrossEncoderModel:
    global _cross
    if _cross is None:
        _cross = CrossEncoderModel()
    return _cross

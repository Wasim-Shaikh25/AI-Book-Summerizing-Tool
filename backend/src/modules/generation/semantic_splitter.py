"""Semantic sentence-level section splitter for pre-LLM source chunking.

Splits sections that exceed ``threshold`` characters into semantically coherent
sub-chunks by detecting topic-shift boundaries in embedding space. Falls back to
equal-character splitting when sentence-transformers is unavailable.

All splitting decisions are driven by measured text properties (character length,
sentence-boundary heuristics, cosine distance between sentence-window embeddings).
No subject vocabulary or domain keywords are used.

Activated by ``SEMANTIC_SPLIT_ENABLED=1`` in environment. Off by default.
"""

from __future__ import annotations

import re
import threading
from typing import Any

_SENT_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_ABBREV_RE = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|et\s+al|e\.g|i\.e|viz|fig|No|Vol|pp|ch|pt|St)\.",
    re.IGNORECASE,
)
_PLACEHOLDER = "\x00"

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_encoder: Any = None
_encoder_lock = threading.Lock()


def _get_encoder() -> Any:
    """Lazy-load MiniLM encoder. Returns None if sentence-transformers is not installed."""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
    except Exception:
        return None
    with _encoder_lock:
        if _encoder is None:
            try:
                _encoder = SentenceTransformer(_MODEL_NAME)
            except Exception:
                return None
    return _encoder


def _sentence_tokenize(text: str) -> list[str]:
    """Split on sentence-ending punctuation followed by whitespace + capital letter.
    Protects common abbreviations (Mr., Dr., etc.) from triggering false splits.
    """
    masked = _ABBREV_RE.sub(lambda m: m.group(0).replace(".", _PLACEHOLDER), text)
    parts = _SENT_END_RE.split(masked)
    restored = [p.replace(_PLACEHOLDER, ".") for p in parts]
    return [s.strip() for s in restored if s.strip()]


def _embed_windows(sentences: list[str], window: int = 3) -> list[list[float]]:
    """Embed overlapping windows of `window` consecutive sentences.
    Returns one embedding vector per boundary position between sentences.
    Returns [] if encoder unavailable.
    """
    model = _get_encoder()
    if model is None or len(sentences) < 2:
        return []
    try:
        import numpy as np  # type: ignore[import-untyped]
    except Exception:
        return []
    texts = []
    n = len(sentences)
    for i in range(n):
        start = max(0, i - window // 2)
        end = min(n, i + window // 2 + 1)
        texts.append(" ".join(sentences[start:end]))
    try:
        vecs = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]
    except Exception:
        return []


def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. Returns 0.0 on zero vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a < 1e-10 or mag_b < 1e-10:
        return 0.0
    return dot / (mag_a * mag_b)


def _find_drop_points(embeddings: list[list[float]], *, n_splits: int) -> list[int]:
    """Return sentence indices of the n_splits lowest cosine-similarity transitions.
    Indices are positions between sent[i] and sent[i+1].
    """
    if len(embeddings) < 2 or n_splits < 1:
        return []
    sims = [
        (i, _cosine(embeddings[i], embeddings[i + 1]))
        for i in range(len(embeddings) - 1)
    ]
    sims.sort(key=lambda x: x[1])
    drop = sorted(idx for idx, _ in sims[:n_splits])
    return drop


def _char_split_fallback(
    text: str,
    *,
    max_chunks: int,
    overlap_sents: int = 0,
) -> list[dict]:
    """Equal-character split when embeddings unavailable. Sentence-aligns boundaries."""
    sents = _sentence_tokenize(text)
    if len(sents) <= 1:
        return [{"text": text, "sub_heading_hint": None}]

    chunk_size = max(1, len(sents) // max_chunks)
    boundaries: list[int] = []
    i = chunk_size
    while i < len(sents) and len(boundaries) < max_chunks - 1:
        boundaries.append(i)
        i += chunk_size

    return _build_chunks(sents, boundaries, overlap_sents=overlap_sents)


def _build_chunks(
    sentences: list[str],
    split_points: list[int],
    *,
    overlap_sents: int = 1,
) -> list[dict]:
    """Construct chunk dicts from sentence list and split-point indices."""
    boundaries = [0] + split_points + [len(sentences)]
    chunks = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        # Add overlap from the previous chunk's tail
        if overlap_sents and i > 0:
            overlap_start = max(boundaries[i] - overlap_sents, boundaries[i - 1])
            chunk_sents = sentences[overlap_start:end]
        else:
            chunk_sents = sentences[start:end]
        if not chunk_sents:
            continue
        body = " ".join(chunk_sents)
        words = body.split()
        hint = " ".join(words[:8]) if words else None
        chunks.append({"text": body, "sub_heading_hint": hint})
    return chunks if chunks else [{"text": " ".join(sentences), "sub_heading_hint": None}]


def semantic_split_section(
    text: str,
    heading: str,
    *,
    threshold: int = 2000,
    max_chunks: int = 4,
    overlap_sents: int = 1,
) -> list[dict]:
    """Split a section into semantically coherent sub-chunks when it exceeds threshold.

    Returns list of {"text": str, "sub_heading_hint": str | None}.

    If len(text) <= threshold:
        Returns [{"text": text, "sub_heading_hint": None}] — passthrough, no split.

    Falls back to equal-character split when sentence-transformers is unavailable.

    Args:
        text:         Section source text.
        heading:      Section heading (used for context only, not currently embedded).
        threshold:    Min chars before splitting is attempted.
        max_chunks:   Maximum number of chunks to produce.
        overlap_sents: Sentences from the previous chunk appended to the next.

    Returns:
        Non-empty list of chunk dicts. Never returns [].
    """
    if not text:
        return [{"text": text, "sub_heading_hint": None}]

    if len(text) <= threshold:
        return [{"text": text, "sub_heading_hint": None}]

    sentences = _sentence_tokenize(text)
    if len(sentences) <= 1:
        return [{"text": text, "sub_heading_hint": None}]

    n_splits = min(max_chunks - 1, len(sentences) - 1)
    if n_splits < 1:
        return [{"text": text, "sub_heading_hint": None}]

    embeddings = _embed_windows(sentences, window=3)
    if not embeddings:
        return _char_split_fallback(text, max_chunks=max_chunks, overlap_sents=overlap_sents)

    drop_points = _find_drop_points(embeddings, n_splits=n_splits)
    if not drop_points:
        return _char_split_fallback(text, max_chunks=max_chunks, overlap_sents=overlap_sents)

    chunks = _build_chunks(sentences, drop_points, overlap_sents=overlap_sents)
    return chunks if chunks else [{"text": text, "sub_heading_hint": None}]

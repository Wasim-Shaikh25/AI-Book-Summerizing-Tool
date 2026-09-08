"""Build indexable RAG chunks from rewrite sections.

Supports three chunk strategies controlled by RAG_CHUNK_STRATEGY env var:
  - ``section`` (default) — one chunk per section body (original behaviour)
  - ``paragraph``          — split on blank lines
  - ``semantic``           — sentence-boundary-aware splits with overlap
"""

from __future__ import annotations

import hashlib
import re as _re
from typing import Any, Dict, List, Sequence

try:
    from src import config
except Exception:  # pragma: no cover — standalone use without full src tree
    config = None  # type: ignore[assignment]

_PARA_SPLIT_RE = _re.compile(r"\n{2,}")
_SENT_END_RE = _re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _semantic_boundary_split(
    text: str,
    heading: str,
    *,
    target_chars: int = 500,
    overlap_sents: int = 1,
) -> list[dict]:
    """Split a section body into paragraph/sentence-aligned chunks.

    Algorithm:
    1. Split by blank lines (paragraph boundaries).
    2. If a paragraph > target_chars: split on sentence boundaries using regex.
    3. Add overlap_sents from the previous chunk at each boundary.
    4. Return list of {"text": str, "paragraph_idx": int,
                       "sentence_start": int, "sentence_end": int,
                       "chunk_strategy": "semantic"}.
    """
    paras = [p.strip() for p in _PARA_SPLIT_RE.split(text or "") if p.strip()]
    if not paras:
        return [{"text": text, "paragraph_idx": 0, "sentence_start": 0,
                 "sentence_end": 0, "chunk_strategy": "semantic"}]

    result: list[dict] = []
    sent_offset = 0

    for p_idx, para in enumerate(paras):
        if len(para) <= target_chars:
            result.append({
                "text": para,
                "paragraph_idx": p_idx,
                "sentence_start": sent_offset,
                "sentence_end": sent_offset,
                "chunk_strategy": "semantic",
            })
            sent_offset += 1
        else:
            sents = [s.strip() for s in _SENT_END_RE.split(para) if s.strip()]
            for s_idx, sent in enumerate(sents):
                overlap_prefix = ""
                if overlap_sents > 0 and s_idx > 0:
                    prev = sents[max(0, s_idx - overlap_sents): s_idx]
                    overlap_prefix = " ".join(prev) + " "
                chunk_text = (overlap_prefix + sent).strip()
                result.append({
                    "text": chunk_text,
                    "paragraph_idx": p_idx,
                    "sentence_start": sent_offset + s_idx,
                    "sentence_end": sent_offset + s_idx,
                    "chunk_strategy": "semantic",
                })
            sent_offset += len(sents)

    return result


def _split_words(text: str, *, size: int, overlap: int) -> List[str]:
    words = (text or "").split()
    if not words or size <= 0:
        return [text] if text.strip() else []
    if len(words) <= size:
        return [" ".join(words)]
    step = max(1, size - max(0, overlap))
    parts: List[str] = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + size]).strip()
        if chunk:
            parts.append(chunk)
        if start + size >= len(words):
            break
    return parts


def sections_to_rag_chunks(
    sections: Sequence[Dict[str, Any]],
    *,
    book_id: str,
    chunk_size_words: int = 0,
    chunk_overlap_words: int = 0,
    min_chars: int = 40,
) -> List[Dict[str, Any]]:
    """Convert pipeline sections into RAG chunk records."""
    chunks: List[Dict[str, Any]] = []
    seq = 0
    for sec in sections:
        heading = str(sec.get("heading") or "").strip()
        body = str(sec.get("text") or "").strip()
        if not heading or len(body) < min_chars:
            continue
        sid = str(sec.get("section_id") or sec.get("section_id") or "")
        chapter = str(sec.get("chapter_heading") or "").strip()
        page = sec.get("page_number")

        # Determine chunk strategy — env / config override; default is "section"
        strategy = str(getattr(config, "RAG_CHUNK_STRATEGY", "section") or "section").lower()

        if strategy == "semantic":
            target_chars = int(getattr(config, "RAG_SEMANTIC_CHUNK_TARGET_CHARS", 500) or 500)
            overlap_sents = int(getattr(config, "RAG_SEMANTIC_OVERLAP_SENTS", 1) or 1)
            sub_chunks = _semantic_boundary_split(
                body, heading,
                target_chars=target_chars,
                overlap_sents=overlap_sents,
            )
        elif strategy == "paragraph":
            paras = [p.strip() for p in body.split("\n\n") if p.strip()]
            if not paras:
                paras = [body]
            sub_chunks = [
                {"text": p, "paragraph_idx": i, "sentence_start": 0,
                 "sentence_end": 0, "chunk_strategy": "paragraph"}
                for i, p in enumerate(paras)
            ]
        elif chunk_size_words > 0:
            # Legacy word-window split (when RAG_CHUNK_SIZE_WORDS is set)
            word_parts = _split_words(body, size=chunk_size_words, overlap=chunk_overlap_words)
            sub_chunks = [
                {"text": p, "paragraph_idx": i, "sentence_start": 0,
                 "sentence_end": 0, "chunk_strategy": "word_window"}
                for i, p in enumerate(word_parts)
            ]
        else:
            sub_chunks = [{"text": body, "paragraph_idx": 0, "sentence_start": 0,
                           "sentence_end": 0, "chunk_strategy": "section"}]

        for part_idx, sub in enumerate(sub_chunks, start=1):
            part = sub["text"]
            seq += 1
            chunk_id = f"{book_id}:RC{seq:05d}"
            embed_text = f"{heading}\n{chapter}\n{part}".strip()
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "book_id": book_id,
                    "section_id": sid,
                    "heading": heading,
                    "chapter_heading": chapter,
                    "page_number": page,
                    "part_no": part_idx,
                    "paragraph_idx": sub.get("paragraph_idx", 0),
                    "sentence_start": sub.get("sentence_start", 0),
                    "sentence_end": sub.get("sentence_end", 0),
                    "chunk_strategy": sub.get("chunk_strategy", "section"),
                    "text": part,
                    "embed_text": embed_text,
                    "char_count": len(part),
                    "text_hash": hashlib.sha256(part.encode("utf-8")).hexdigest(),
                }
            )
    return chunks

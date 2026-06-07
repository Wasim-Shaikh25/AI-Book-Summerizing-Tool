"""Build indexable RAG chunks from rewrite sections."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Sequence


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

        if chunk_size_words > 0:
            bodies = _split_words(body, size=chunk_size_words, overlap=chunk_overlap_words)
        else:
            bodies = [body]

        for part_idx, part in enumerate(bodies, start=1):
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
                    "text": part,
                    "embed_text": embed_text,
                    "char_count": len(part),
                    "text_hash": hashlib.sha256(part.encode("utf-8")).hexdigest(),
                }
            )
    return chunks

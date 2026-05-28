"""Deterministic line signals for Stage 15b doubted-section resolver."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set

_METADATA_RE = re.compile(
    r"\bISBN\b|\b©\b|copyright|all rights reserved|published by|publisher"
    r"|edition\b|printed in|www\.|\.com\b|\.in\b",
    re.I,
)
_TOC_RE = re.compile(
    r"\.{2,}\s*\d+\s*$|^\s*contents\s*$|^\s*index\s*$|^\s*table of contents",
    re.I,
)
_CHAPTER_RE = re.compile(r"^chapter\s+\d+\b", re.I)
_LEGAL_RE = re.compile(
    r"\bv\.\s+[A-Z]|\bAIR\s+\d{4}\b|\bSCC\b|\(\d{4}\)\s+\d+\s+[A-Z]+",
)


def compute_line_signals(
    *,
    text: str,
    page_number: int,
    is_bold: bool,
    word_count_hint: Optional[int] = None,
    confirmed_heading_texts: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    t = (text or "").strip()
    wc = word_count_hint if word_count_hint is not None else len(t.split())

    metadata_score = 0
    toc_score = 0
    content_score = 0

    if _METADATA_RE.search(t):
        metadata_score += 3
    if page_number <= 2 and wc <= 12 and not _LEGAL_RE.search(t):
        metadata_score += 1
    if re.search(r"^\d{1,3}\s*$", t):
        metadata_score += 1

    if _TOC_RE.search(t):
        toc_score += 3
    if re.search(r"\.{3,}", t):
        toc_score += 2
    if re.match(r"^\d+(\.\d+)*\s+\S", t) and re.search(r"\s+\d+\s*$", t):
        toc_score += 2

    if _LEGAL_RE.search(t):
        content_score += 3
    if _CHAPTER_RE.match(t):
        content_score += 2
    if is_bold and wc <= 12 and not _TOC_RE.search(t):
        content_score += 1
    if wc >= 20 and not _METADATA_RE.search(t):
        content_score += 1

    if confirmed_heading_texts and t in confirmed_heading_texts:
        content_score += 2

    annotation = "[META]" if metadata_score >= max(toc_score, content_score) else "[TOC]" if toc_score >= content_score else "[BODY]"
    return {
        "metadata_score": metadata_score,
        "toc_score": toc_score,
        "content_score": content_score,
        "annotation": annotation,
    }

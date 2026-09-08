"""Detect when a PDF needs ML layout parsing (scanned / image-only pages)."""

from __future__ import annotations

from typing import Any, Dict, List


def _page_text_char_count(page_dict: Dict[str, Any]) -> int:
    total = 0
    for block in page_dict.get("blocks") or []:
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            if not isinstance(line, dict):
                continue
            for span in line.get("spans") or []:
                if isinstance(span, dict):
                    total += len(str(span.get("text") or "").strip())
    return total


def pdf_likely_scanned(
    pages_dict: List[Dict[str, Any]],
    *,
    min_text_chars: int = 40,
    scan_ratio: float = 0.5,
) -> bool:
    """True when most sampled pages have very little extractable text (scan-like)."""
    if not pages_dict:
        return False
    scanned = sum(1 for p in pages_dict if _page_text_char_count(p) < min_text_chars)
    threshold = max(1, int(len(pages_dict) * scan_ratio))
    return scanned >= threshold

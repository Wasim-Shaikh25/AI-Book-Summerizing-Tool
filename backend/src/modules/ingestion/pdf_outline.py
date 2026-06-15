"""PDF embedded bookmark/outline helpers for TOC fallback."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import fitz

from src.shared.models import FinalHeading, NormalizedLine

_NORM_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _NORM_WS.sub(" ", (text or "").strip().lower())


def extract_pdf_outline(pdf_path: str) -> List[Dict[str, Any]]:
    """Return embedded PDF outline entries: level, title, page (1-based)."""
    doc = fitz.open(pdf_path)
    try:
        raw = doc.get_toc(simple=False) or []
        out: List[Dict[str, Any]] = []
        for row in raw:
            if len(row) < 3:
                continue
            level, title, page = row[0], row[1], row[2]
            title_s = str(title or "").strip()
            if not title_s:
                continue
            out.append(
                {
                    "level": int(level),
                    "title": title_s,
                    "page": int(page),
                    "source": "pdf_outline",
                }
            )
        return out
    finally:
        doc.close()


def _heading_page(h: Any, layout_by_page: Dict[int, List[NormalizedLine]]) -> Optional[int]:
    if isinstance(h, FinalHeading):
        lid = getattr(h, "line_id", None)
    elif isinstance(h, dict):
        lid = h.get("line_id")
    else:
        lid = getattr(h, "line_id", None)
    if not isinstance(lid, int):
        return None
    for page, lines in layout_by_page.items():
        if any(ln.line_id == lid for ln in lines):
            return page
    return None


def _lines_on_page(lines: Sequence[NormalizedLine], page: int) -> List[NormalizedLine]:
    return [ln for ln in lines if int(getattr(ln, "page_number", 0) or 0) == page]


def _best_line_match(title: str, candidates: Sequence[NormalizedLine], *, min_ratio: float = 0.72) -> Optional[int]:
    target = _norm(title)
    if not target:
        return None
    best_id: Optional[int] = None
    best_score = 0.0
    for ln in candidates:
        text = _norm(ln.text)
        if not text:
            continue
        if text == target:
            return ln.line_id
        score = SequenceMatcher(None, target, text).ratio()
        if target in text or text in target:
            score = max(score, 0.85)
        if score > best_score:
            best_score = score
            best_id = ln.line_id
    if best_score >= min_ratio:
        return best_id
    return None


def supplement_toc_from_pdf_outline(
    pdf_path: str,
    lines: Sequence[NormalizedLine],
    final_headings: Sequence[Any],
    existing_seed_ids: Set[int],
    *,
    min_outline_entries: int = 3,
    max_supplement: int = 40,
) -> Tuple[Set[int], List[Dict[str, Any]]]:
    """
    When deterministic TOC finds few seeds, match PDF bookmark titles to heading line_ids.

    Returns updated seed ids and log records.
    """
    log: List[Dict[str, Any]] = []
    try:
        outline = extract_pdf_outline(pdf_path)
    except Exception as exc:
        log.append({"kind": "pdf_outline_skip", "reason": "extract_failed", "error": str(exc)})
        return set(existing_seed_ids), log

    if len(outline) < min_outline_entries:
        log.append({"kind": "pdf_outline_skip", "reason": "too_few_outline_entries", "count": len(outline)})
        return set(existing_seed_ids), log

    if len(existing_seed_ids) >= min_outline_entries:
        log.append({"kind": "pdf_outline_skip", "reason": "deterministic_toc_sufficient", "seed_count": len(existing_seed_ids)})
        return set(existing_seed_ids), log

    pages_map: Dict[int, List[NormalizedLine]] = {}
    for ln in lines:
        pg = int(getattr(ln, "page_number", 0) or 0)
        if pg:
            pages_map.setdefault(pg, []).append(ln)

    heading_ids = {
        int(h.get("line_id") if isinstance(h, dict) else getattr(h, "line_id", 0))
        for h in final_headings
        if (isinstance(h, dict) and isinstance(h.get("line_id"), int))
        or (not isinstance(h, dict) and isinstance(getattr(h, "line_id", None), int))
    }

    supplemented: Set[int] = set(existing_seed_ids)
    added = 0

    for entry in outline:
        if added >= max_supplement:
            break
        page = int(entry.get("page") or 0)
        title = str(entry.get("title") or "")
        if not page or not title:
            continue
        page_lines = _lines_on_page(lines, page)
        if not page_lines:
            continue
        # Prefer matching among final headings on/near that page
        near_lines = page_lines
        if page > 1:
            near_lines = _lines_on_page(lines, page) + _lines_on_page(lines, page - 1) + _lines_on_page(lines, page + 1)
        lid = _best_line_match(title, near_lines)
        if lid is None or lid not in heading_ids:
            continue
        if lid in supplemented:
            continue
        supplemented.add(lid)
        added += 1
        log.append(
            {
                "kind": "pdf_outline_seed",
                "line_id": lid,
                "title": title,
                "page": page,
                "level": entry.get("level"),
            }
        )

    log.insert(
        0,
        {
            "kind": "pdf_outline_summary",
            "outline_entries": len(outline),
            "existing_seeds": len(existing_seed_ids),
            "added_seeds": added,
            "total_seeds": len(supplemented),
        },
    )
    return supplemented, log

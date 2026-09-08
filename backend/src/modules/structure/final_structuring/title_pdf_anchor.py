"""PDF-anchored acceptance for LLM-edited titles (subject-agnostic substring check)."""

from __future__ import annotations

import re
from typing import Optional, Sequence

from src.shared.models import NormalizedLine


def _norm_match(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def title_found_in_lines(
    title: str,
    lines: Sequence[NormalizedLine],
    *,
    page_number: Optional[int] = None,
    margin_pages: int = 1,
) -> bool:
    """True when any normalized substring of *title* appears on a line in the page window."""
    needle = _norm_match(title)
    if len(needle) < 4:
        return False

    page_min = page_max = None
    if isinstance(page_number, int) and page_number > 0:
        page_min = max(1, page_number - margin_pages)
        page_max = page_number + margin_pages

    fragments: list[str] = [needle]
    words = needle.split()
    if len(words) >= 4:
        fragments.append(" ".join(words[:6]))
    if len(words) >= 2:
        fragments.append(" ".join(words[:3]))

    for line in lines:
        pg = getattr(line, "page_number", None)
        if page_min is not None and page_max is not None:
            if not isinstance(pg, int) or pg < page_min or pg > page_max:
                continue
        hay = _norm_match(str(getattr(line, "text", "") or ""))
        if not hay:
            continue
        for frag in fragments:
            if len(frag) >= 4 and frag in hay:
                return True
    return False


def accept_edited_title(
    proposed: str,
    local_title: str,
    *,
    lines: Optional[Sequence[NormalizedLine]] = None,
    page_number: Optional[int] = None,
    require_strict: bool = False,
) -> str:
    """Return *proposed* only when strict gate passes or is off; else *local_title*."""
    proposed = (proposed or "").strip()
    local_title = (local_title or "").strip()
    if not proposed:
        return local_title
    if not require_strict or not lines:
        return proposed
    if title_found_in_lines(proposed, lines, page_number=page_number):
        return proposed
    return local_title or proposed

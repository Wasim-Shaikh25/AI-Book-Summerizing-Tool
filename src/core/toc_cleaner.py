from __future__ import annotations

from typing import Dict, List, Sequence

from .models import FinalHeading, Fragment


def clean_toc(
    headings: Sequence[FinalHeading],
    fragments: Sequence[Fragment] | None = None,
    *,
    fragment_text_by_id: Dict[str, str] | None = None,
    min_fragment_chars: int = 20,
) -> List[FinalHeading]:
    """
    Removes TOC-only entries.

    Rule:
      Remove headings that have fragment text length < min_fragment_chars
      AND are followed by another heading with content.
      Never remove the first heading.

    Notes:
      Fragment text can be provided via:
        - `fragments` (list of Fragment)
        - `fragment_text_by_id` mapping
      If neither is provided, headings are returned unchanged.
    """
    if len(headings) <= 1:
        return list(headings)

    text_by_fragment_id: Dict[str, str] = {}

    if fragment_text_by_id is not None:
        text_by_fragment_id.update(fragment_text_by_id)

    if fragments is not None:
        for f in fragments:
            text_by_fragment_id[f.fragment_id] = f.text

    if not text_by_fragment_id:
        return list(headings)

    # Compute content lengths per heading
    def _frag_len(h: FinalHeading) -> int:
        if not h.fragment_id:
            return 0
        return len(text_by_fragment_id.get(h.fragment_id, ""))

    cleaned: List[FinalHeading] = []
    cleaned.append(headings[0])  # Never remove the first heading

    for i in range(1, len(headings)):
        h = headings[i]
        cur_len = _frag_len(h)

        # Determine if there exists a "next heading with content"
        next_has_content = False
        for j in range(i + 1, len(headings)):
            if _frag_len(headings[j]) >= min_fragment_chars:
                next_has_content = True
                break

        should_remove = cur_len < min_fragment_chars and next_has_content

        if not should_remove:
            cleaned.append(h)

    return cleaned

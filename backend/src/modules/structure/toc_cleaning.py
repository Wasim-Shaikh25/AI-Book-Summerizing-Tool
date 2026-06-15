from __future__ import annotations

from typing import List, Sequence

from src.shared.models import FinalHeading, Fragment


def clean_toc(
    headings: Sequence[FinalHeading],
    fragments: Sequence[Fragment] | None = None,
    *,
    fragment_text_by_id: dict | None = None,
    _min_fragment_chars: int = 20,
    _min_lines_after_heading: int = 3,
) -> List[FinalHeading]:
    """Identity pass — headings unchanged (dedupe logic removed; unused since 2026-03)."""
    return list(headings)

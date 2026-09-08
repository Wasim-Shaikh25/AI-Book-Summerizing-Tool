"""Document-wide contents / index page detection.

The repeated-heading TOC detector (`toc_repeat_detection.py`) catches the
front-matter table of contents. Some documents (e.g. bare acts) also carry
*per-chapter* index pages mid-document — a page that is mostly enumerated title
rows (``65. Punishment for rape``). Those headings are not always repeated
elsewhere, so they slip past the repeated-heading detector and become noisy,
ungrounded sections.

This detector is page-based and measured only: a page whose non-noise lines are
dominated by enumerated title rows is treated as a contents region, and all its
line ids are returned so the partitioner can exclude them. No subject
vocabulary is used.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Sequence, Set, Tuple

from src.shared.models import NormalizedLine
from src.shared.text_grounding import is_enumerated_title_line

# A page must have at least this many enumerated rows, and that fraction of its
# non-noise lines, to count as a contents/index page.
_MIN_ENUM_LINES = 5
_MIN_ENUM_RATIO = 0.5


def detect_contents_regions(
    lines: Sequence[NormalizedLine],
    *,
    min_enum_lines: int = _MIN_ENUM_LINES,
    enum_ratio: float = _MIN_ENUM_RATIO,
) -> Tuple[Set[int], List[Dict[str, Any]]]:
    """Find pages dominated by enumerated title rows.

    Returns:
        region_line_ids: line ids on detected contents/index pages.
        log_items: envelope records describing each detected page.
    """
    if not lines:
        return set(), []

    by_page: Dict[Any, List[NormalizedLine]] = defaultdict(list)
    for ln in lines:
        by_page[getattr(ln, "page_number", None)].append(ln)

    region_line_ids: Set[int] = set()
    log_items: List[Dict[str, Any]] = []

    for page, page_lines in by_page.items():
        non_noise = [
            ln
            for ln in page_lines
            if (ln.text or "").strip() and not getattr(ln, "is_noise", False)
        ]
        if len(non_noise) < min_enum_lines:
            continue
        enum_count = sum(1 for ln in non_noise if is_enumerated_title_line(ln.text))
        if enum_count < min_enum_lines:
            continue
        ratio = enum_count / len(non_noise)
        if ratio < enum_ratio:
            continue
        for ln in non_noise:
            region_line_ids.add(ln.line_id)
        log_items.append(
            {
                "kind": "contents_region_page",
                "page_number": page,
                "non_noise_line_count": len(non_noise),
                "enumerated_line_count": enum_count,
                "enumerated_ratio": round(ratio, 3),
                "line_ids": sorted(ln.line_id for ln in non_noise),
            }
        )

    return region_line_ids, log_items

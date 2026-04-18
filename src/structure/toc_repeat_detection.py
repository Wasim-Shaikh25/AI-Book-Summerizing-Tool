"""
Deterministic TOC detection (no LLM).

Seed rule — for each final heading at line L:
1. Heading line text (stripped) must appear at least twice among all PDF lines.
2. The next line in document order must also appear at least twice.
3. The previous line must not look like another numbered outline row (e.g. ``1.2 …``),
   so consecutive syllabus/TOC list rows are not all marked as seeds—only the first
   row after a non-numbered line qualifies.
If any check fails, the heading is not marked as TOC (`is_toc`).

Section spans — for each normalized heading text that has at least one `is_toc`
heading, take the first `is_toc` occurrence of that text, then the next final
heading with the same text; all lines from the first up to (but not including)
that second heading line are one TOC section (`in_toc_section` for headings
in that range). Same rule for every such repeating heading text.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Set, Tuple

from src.core.models import FinalHeading, NormalizedLine


def _norm(s: str) -> str:
    return (s or "").strip()


# Syllabus / outline rows usually start with "1.2", "2.3.1", etc. Used to break false seed chains.
_RE_NUMBERED_OUTLINE_START = re.compile(r"^\d+(?:\.\d+)+\b")


def _looks_like_numbered_outline_line(text: str) -> bool:
    t = _norm(text)
    return bool(t and _RE_NUMBERED_OUTLINE_START.match(t))


def _heading_line_id(h: Any) -> int | None:
    if isinstance(h, FinalHeading):
        lid = getattr(h, "line_id", None)
        return int(lid) if isinstance(lid, int) else None
    if isinstance(h, dict):
        lid = h.get("line_id")
        return int(lid) if isinstance(lid, int) else None
    lid = getattr(h, "line_id", None)
    return int(lid) if isinstance(lid, int) else None


def detect_deterministic_toc(
    lines: List[NormalizedLine],
    final_headings: List[Any],
) -> Tuple[Set[int], List[Dict[str, Any]]]:
    """
    Returns:
        toc_seed_line_ids: heading lines that pass the two-line duplicate heuristic.
        log_items: envelope items for 10_deterministic_toc.json (seed_heading only).
    """
    if not lines:
        return set(), []

    counts = Counter(_norm(ln.text) for ln in lines)
    by_id: Dict[int, NormalizedLine] = {ln.line_id: ln for ln in lines}
    index_by_id = {ln.line_id: i for i, ln in enumerate(lines)}

    toc_seed_line_ids: Set[int] = set()
    seed_records: List[Dict[str, Any]] = []

    for h in final_headings:
        lid = _heading_line_id(h)
        if lid is None or lid not in by_id:
            continue
        t = _norm(by_id[lid].text)
        if not t:
            continue
        if counts[t] < 2:
            continue

        idx = index_by_id.get(lid)
        if idx is None:
            continue
        if idx + 1 >= len(lines):
            continue
        t2 = _norm(lines[idx + 1].text)
        if not t2 or counts[t2] < 2:
            continue

        if idx > 0 and _looks_like_numbered_outline_line(lines[idx - 1].text):
            continue

        toc_seed_line_ids.add(lid)
        seed_records.append(
            {
                "kind": "seed_heading",
                "page_number": by_id[lid].page_number,
                "heading_text": t,
                "heading_text_occurrences": counts[t],
                "second_line_text": t2,
                "second_line_occurrences": counts[t2],
            }
        )

    return toc_seed_line_ids, seed_records


def _heading_text_norm(h: Any) -> str:
    if isinstance(h, dict):
        return _norm(str(h.get("text", "")))
    return _norm(str(getattr(h, "text", "")))


def _is_toc_flag(h: Any) -> bool:
    if isinstance(h, dict):
        return bool(h.get("is_toc"))
    return bool(getattr(h, "is_toc", False))


def build_toc_sections_from_repeated_headings(
    lines: List[NormalizedLine],
    final_headings: List[Any],
) -> Tuple[Set[int], List[Dict[str, Any]]]:
    """
    For each normalized heading text T with at least one is_toc heading:
    - start = first line_id (document order) where a final heading has text T and is_toc
    - end_exclusive = line_id of the next final heading with text T after start
    - Section lines: every line from document index of `start` up to but not including
      the line index of `end_exclusive`

    Returns all line_ids belonging to any such section, plus toc_section_span log items.
    """
    if not lines:
        return set(), []

    index_by_lid = {ln.line_id: i for i, ln in enumerate(lines)}

    rows: List[Tuple[int, bool, str]] = []
    for h in final_headings:
        lid = _heading_line_id(h)
        if lid is None:
            continue
        t = _heading_text_norm(h)
        if not t:
            continue
        rows.append((lid, _is_toc_flag(h), t))

    rows.sort(key=lambda x: x[0])

    by_text: Dict[str, List[Tuple[int, bool]]] = {}
    for lid, it, t in rows:
        by_text.setdefault(t, []).append((lid, it))

    section_line_ids: Set[int] = set()
    span_records: List[Dict[str, Any]] = []

    for T, lst in by_text.items():
        lst.sort(key=lambda x: x[0])
        toc_lids = [lid for lid, is_t in lst if is_t]
        if not toc_lids:
            continue
        start = toc_lids[0]
        all_lids = [lid for lid, _ in lst]
        later = [lid for lid in all_lids if lid > start]
        if not later:
            continue
        end_ex = later[0]

        i0 = index_by_lid.get(start)
        i1 = index_by_lid.get(end_ex)
        if i0 is None or i1 is None or i0 >= i1:
            continue

        for j in range(i0, i1):
            section_line_ids.add(lines[j].line_id)

        last_inclusive = lines[i1 - 1].line_id
        span_records.append(
            {
                "kind": "toc_section_span",
                "heading_text": T,
                "page_number_start": lines[i0].page_number,
                "page_number_end": lines[i1 - 1].page_number,
                "start_line_id": start,
                "end_line_id_inclusive": last_inclusive,
                "repeat_heading_line_id": end_ex,
                "line_count": i1 - i0,
            }
        )

    return section_line_ids, span_records


def book_metadata_from_first_toc_section(
    lines: List[NormalizedLine],
    span_records: List[Dict[str, Any]],
) -> Tuple[Set[int], List[Dict[str, Any]]]:
    """
    Book-level metadata for the opening of the document:

    1) **Document prefix** — every line from the start of the PDF line list up to
       (but not including) the first line of the earliest TOC section, excluding noise.
       Captures title blocks like "LAW OF TORTS…", "MODULE 1:", etc.

    2) **First TOC section** — same as the first ``toc_section_span`` (non-noise lines only),
       from first ``is_toc`` heading for that text until before the repeated heading.

    Later TOC sections are not included.
    """
    spans = [r for r in span_records if r.get("kind") == "toc_section_span"]
    if not lines or not spans:
        return set(), []

    first = min(spans, key=lambda r: int(r["start_line_id"]))
    index_by_lid = {ln.line_id: i for i, ln in enumerate(lines)}
    start = int(first["start_line_id"])
    end_ex = int(first["repeat_heading_line_id"])

    i0 = index_by_lid.get(start)
    i1 = index_by_lid.get(end_ex)
    if i0 is None or i1 is None or i0 >= i1:
        return set(), []

    meta_ids: Set[int] = set()

    for j in range(0, i0):
        ln = lines[j]
        if getattr(ln, "is_noise", False):
            continue
        meta_ids.add(ln.line_id)

    for j in range(i0, i1):
        ln = lines[j]
        if getattr(ln, "is_noise", False):
            continue
        meta_ids.add(ln.line_id)

    last_inc = lines[i1 - 1].line_id
    log_item: Dict[str, Any] = {
        "kind": "book_metadata_first_toc",
        "source": "document_prefix_and_first_toc_section_excluding_noise",
        "heading_text": first.get("heading_text"),
        "page_number_start": first.get("page_number_start"),
        "page_number_end": first.get("page_number_end"),
        "first_toc_section_start_line_id": start,
        "first_toc_section_end_line_id_inclusive": last_inc,
        "repeat_heading_line_id": end_ex,
        "non_noise_line_count": len(meta_ids),
    }
    if i0 > 0:
        log_item["document_prefix_start_line_id"] = lines[0].line_id
        log_item["document_prefix_end_line_id_inclusive"] = lines[i0 - 1].line_id
    return meta_ids, [log_item]

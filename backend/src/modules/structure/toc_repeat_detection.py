"""
Deterministic TOC detection (no LLM).

Seed rule — for each final heading at line L:
1. Heading line text (stripped) must appear at least twice among all PDF lines.
2. The next line in document order must also appear at least twice.
3. The previous line must not look like another numbered outline row (e.g. ``1.2 …``),
   so consecutive outline/TOC list rows are not all marked as seeds—only the first
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
from typing import Any, Dict, List, Optional, Set, Tuple

from src.shared.models import FinalHeading, NormalizedLine, Fragment


def _norm(s: str) -> str:
    s = (s or "").strip()
    # Collapse decimal section numbers with internal spaces: "3. 4" -> "3.4"
    s = re.sub(r'(\d)\.\s+(\d)', r'\1.\2', s)
    # Add space after comma before digit: "Act,1988" -> "Act, 1988"
    s = re.sub(r',(\d)', r', \1', s)
    # Normalize runs of whitespace to a single space and spacing around & for consistent matching
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\s*&\s*', ' & ', s)
    # Strip trailing period: "...Councils." == "...Councils" for matching purposes
    s = re.sub(r'\.\s*$', '', s)
    return s.strip()


# Outline rows usually start with "1.2", "2.3.1", etc. Used to break false seed chains.
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


_MIN_TOC_GROUP_SIZE = 3    # need at least 3 consecutive headings to call it a TOC listing
_MAX_CONSECUTIVE_GAP = 10  # headings <= 10 line_ids apart are considered consecutive


def build_toc_sections_from_repeated_headings(
    lines: List[NormalizedLine],
    final_headings: List[Any],
) -> Tuple[Set[int], List[Dict[str, Any]]]:
    """
    Correct TOC section detection algorithm:

    1. Sort all final headings by line_id.
    2. Find CONSECUTIVE groups: headings where each adjacent pair is within
       _MAX_CONSECUTIVE_GAP line_ids of each other (close together on a TOC page).
    3. For each group of size >= _MIN_TOC_GROUP_SIZE, check if ALL heading texts
       in that group appear at least twice anywhere in the full document.
    4. If yes -> the FIRST such group is a TOC listing. Mark only those specific
       heading line_ids as in_toc_section=True.
    5. The second occurrences of those headings (in the body) are NOT touched —
       they remain as valid body headings.

    This avoids sweeping body content between first and second occurrence.
    """
    if not lines:
        return set(), []

    # Count every text across ALL raw lines (not just headings)
    line_text_counts: Counter = Counter(_norm(ln.text) for ln in lines)
    by_lid: Dict[int, NormalizedLine] = {ln.line_id: ln for ln in lines}

    # Sort headings by line_id
    sorted_heads = sorted(
        [h for h in final_headings if _heading_line_id(h) is not None],
        key=lambda h: _heading_line_id(h),  # type: ignore[arg-type]
    )
    if len(sorted_heads) < _MIN_TOC_GROUP_SIZE:
        return set(), []

    # Step 1: partition into consecutive groups
    groups: List[List[Any]] = []
    current: List[Any] = [sorted_heads[0]]
    for i in range(1, len(sorted_heads)):
        prev_lid = _heading_line_id(sorted_heads[i - 1])
        curr_lid = _heading_line_id(sorted_heads[i])
        if prev_lid is not None and curr_lid is not None and (curr_lid - prev_lid) <= _MAX_CONSECUTIVE_GAP:
            current.append(sorted_heads[i])
        else:
            if len(current) >= _MIN_TOC_GROUP_SIZE:
                groups.append(list(current))
            current = [sorted_heads[i]]
    if len(current) >= _MIN_TOC_GROUP_SIZE:
        groups.append(list(current))

    section_line_ids: Set[int] = set()
    span_records: List[Dict[str, Any]] = []

    # Build per-text occurrence list (all line_ids for each heading text, sorted)
    all_occ: Dict[str, List[int]] = {}
    for h in sorted_heads:
        t = _heading_text_norm(h)
        lid = _heading_line_id(h)
        if t and lid is not None:
            all_occ.setdefault(t, []).append(lid)

    # First-occurrence lookup: smallest line_id per text
    first_occ: Dict[str, int] = {t: lids[0] for t, lids in all_occ.items()}

    # Set of all final heading line_ids (continuation lines must NOT be headings themselves)
    heading_lid_set: Set[int] = {_heading_line_id(h) for h in sorted_heads if _heading_line_id(h) is not None}

    # All known body heading texts (for prefix matching)
    all_heading_texts: Set[str] = set(all_occ.keys())

    # Sorted line_ids for finding the next raw line after a given lid
    sorted_line_ids = sorted(by_lid.keys())
    lid_pos = {lid: i for i, lid in enumerate(sorted_line_ids)}

    def _next_non_heading_line(lid: int) -> Optional[NormalizedLine]:
        """Return the next raw layout line after lid that is not itself a heading."""
        pos = lid_pos.get(lid)
        if pos is None:
            return None
        for i in range(pos + 1, min(pos + 4, len(sorted_line_ids))):
            candidate = by_lid[sorted_line_ids[i]]
            if sorted_line_ids[i] not in heading_lid_set:
                return candidate
        return None

    def _try_continuation(t: str, lid: int) -> Optional[Tuple[str, Optional[int]]]:
        """
        For a truncated heading that fails condition A, try two strategies:

        Case A — TOC text is SHORTER than body heading:
          Check if `t` is a prefix of any known body heading (min 6 words).
          If yes, grab the next non-heading raw line and combine; verify exact match.

        Case B — TOC text is LONGER than body heading:
          Both are truncated from the same long title at different line-break points.
          Check if `t` starts with any known body heading (min 8 words).
          If yes, they're the same section — no continuation line needed.

        Returns (matched_body_heading_text, continuation_line_id_or_None) or None.
        """
        if len(t.split()) < 6:
            return None

        # Case B: t is longer — check if t starts with a known heading (prefix of t)
        for ht in all_heading_texts:
            if ht != t and len(ht.split()) >= 8 and t.startswith(ht):
                return (ht, None)

        # Case A: t is shorter — find any known heading that starts with t.
        # Prefix match alone is sufficient evidence (min 6 words already enforced above).
        for ht in all_heading_texts:
            if ht.startswith(t) and ht != t:
                return (ht, None)
        return None

    # Step 2: for each consecutive group, find the longest qualifying sub-run
    for group in groups:
        # Evaluate each heading: does it satisfy both conditions?
        # Extra: track continuation lines for truncated headings
        qualifies = []
        continuation_lids: Dict[int, int] = {}  # heading_lid -> continuation_lid
        for h in group:
            t = _heading_text_norm(h)
            lid = _heading_line_id(h)
            cond_a = bool(t) and line_text_counts.get(t, 0) >= 2
            cond_b = bool(t) and lid is not None and first_occ.get(t) == lid
            # If cond_a fails but cond_b passes, try continuation-line extension
            if not cond_a and cond_b and t and lid is not None:
                ext = _try_continuation(t, lid)
                if ext is not None:
                    _full_text, cont_lid = ext
                    cond_a = True
                    if cont_lid is not None:
                        continuation_lids[lid] = cont_lid
            qualifies.append(cond_a and cond_b)

        # Slide through to find longest consecutive run of qualifying headings
        best_start = best_end = -1
        run_start = -1
        for i, ok in enumerate(qualifies):
            if ok:
                if run_start < 0:
                    run_start = i
                run_len = i - run_start + 1
                if run_len > best_end - best_start:
                    best_start, best_end = run_start, i
            else:
                run_start = -1

        if best_start < 0 or (best_end - best_start + 1) < _MIN_TOC_GROUP_SIZE:
            continue  # no qualifying sub-run of sufficient size

        toc_sub = group[best_start: best_end + 1]
        lids = [_heading_line_id(h) for h in toc_sub if _heading_line_id(h) is not None]

        # Condition C: second occurrences must NOT be clustered together.
        # In a true TOC each heading reappears in a different chapter (spread far apart).
        # In a repeated template (e.g. "Facts → Issues → Judgment" per case), the second
        # occurrences are also consecutive — detect and reject that pattern.
        second_occ_lids = []
        for h in toc_sub:
            t = _heading_text_norm(h)
            occ = all_occ.get(t, [])
            if len(occ) >= 2:
                second_occ_lids.append(occ[1])
        if second_occ_lids:
            second_spread = max(second_occ_lids) - min(second_occ_lids)
            # Threshold: allow at most group_size * gap lines between second occurrences
            max_spread = len(toc_sub) * _MAX_CONSECUTIVE_GAP
            if second_spread <= max_spread:
                continue  # second occurrences are clustered → repeated template, not TOC

        for lid in lids:
            section_line_ids.add(lid)
            # Also mark continuation lines (second half of a truncated TOC entry)
            if lid in continuation_lids:
                section_line_ids.add(continuation_lids[lid])

        pg_start = (by_lid.get(lids[0]) or NormalizedLine(0, "")).page_number
        pg_end = (by_lid.get(lids[-1]) or NormalizedLine(0, "")).page_number
        texts = [_heading_text_norm(h) for h in toc_sub]
        span_records.append(
            {
                "kind": "toc_section_span",
                "heading_text": texts[0],
                "page_number_start": pg_start,
                "page_number_end": pg_end,
                "start_line_id": lids[0],
                "end_line_id_inclusive": lids[-1],
                "group_size": len(lids),
            }
        )

    return section_line_ids, span_records


def book_metadata_from_first_toc_section(
    lines: List[NormalizedLine],
    span_records: List[Dict[str, Any]],
    headings: Optional[List[FinalHeading]] = None,
    fragments: Optional[List[Fragment]] = None,
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
    end_inc = int(first["end_line_id_inclusive"])

    i0 = index_by_lid.get(start)
    i_end = index_by_lid.get(end_inc)
    if i0 is None or i_end is None:
        return set(), []

    meta_ids: Set[int] = set()

    # Document prefix: all non-noise lines before the first TOC group
    for j in range(0, i0):
        ln = lines[j]
        if not getattr(ln, "is_noise", False):
            meta_ids.add(ln.line_id)

    # First TOC group: lines from start up to and including the last TOC heading
    for j in range(i0, i_end + 1):
        ln = lines[j]
        if not getattr(ln, "is_noise", False):
            meta_ids.add(ln.line_id)

    log_item: Dict[str, Any] = {
        "kind": "book_metadata_first_toc",
        "source": "document_prefix_and_first_toc_section_excluding_noise",
        "heading_text": first.get("heading_text"),
        "page_number_start": first.get("page_number_start"),
        "page_number_end": first.get("page_number_end"),
        "first_toc_section_start_line_id": start,
        "first_toc_section_end_line_id_inclusive": end_inc,
        "non_noise_line_count": len(meta_ids),
    }
    if i0 > 0:
        log_item["document_prefix_start_line_id"] = lines[0].line_id
        log_item["document_prefix_end_line_id_inclusive"] = lines[i0 - 1].line_id
    log_items: List[Dict[str, Any]] = [log_item]

    # Additional metadata from subsequent mini-TOC sections:
    # Policy: For every later TOC span, include ONLY the initial run of headings
    # within that span whose fragments have NO body content (empty normalized text).
    # Stop at the first heading with non-empty fragment text.
    if headings and fragments and len(spans) > 1:
        # Build quick lookups
        frag_by_heading_id: Dict[str, Fragment] = {}
        for f in fragments:
            hid = getattr(f, "assigned_heading_id", None)
            if isinstance(hid, str) and hid:
                frag_by_heading_id[hid] = f

        # Map line_id to NormalizedLine for noise checks
        by_lid: Dict[int, NormalizedLine] = {ln.line_id: ln for ln in lines}

        # All headings sorted by line_id for easy slicing
        all_sorted = sorted(
            [h for h in headings if isinstance(getattr(h, "line_id", None), int)],
            key=lambda hh: int(getattr(hh, "line_id", 0)),
        )

        def _is_empty_frag(h) -> bool:
            hid = getattr(h, "id", None)
            lid = int(getattr(h, "line_id", 0) or 0)
            if not isinstance(hid, str) or lid == 0:
                return False
            ln = by_lid.get(lid)
            if ln is not None and getattr(ln, "is_noise", False):
                return False
            f = frag_by_heading_id.get(hid)
            return (getattr(f, "text", None) or "").strip() == "" if f is not None else False

        sorted_spans = sorted(spans, key=lambda r: int(r["start_line_id"]))

        # Process spans after the first
        for idx, sp in enumerate(sorted_spans[1:], start=1):
            s_lid = int(sp.get("start_line_id"))
            e_lid = int(sp.get("end_line_id_inclusive"))

            # --- PRE-SPAN: walk backwards from span start, collect empty-fragment headings ---
            # Lower bound: end of the previous span (don't go further back into already-classified meta)
            prev_end = int(sorted_spans[idx - 1].get("end_line_id_inclusive"))
            before_span = [
                h for h in all_sorted
                if prev_end < int(getattr(h, "line_id", 0)) < s_lid
            ]
            pre_lids: List[int] = []
            for h in reversed(before_span):
                if _is_empty_frag(h):
                    pre_lids.append(int(getattr(h, "line_id", 0)))
                else:
                    break  # stop at first heading that has body content
            pre_lids.reverse()  # restore ascending order

            # --- IN-SPAN: walk forward inside [s_lid, e_lid], stop at first non-empty ---
            in_span = [h for h in all_sorted if s_lid <= int(getattr(h, "line_id", 0)) <= e_lid]
            in_lids: List[int] = []
            for h in in_span:
                if _is_empty_frag(h):
                    in_lids.append(int(getattr(h, "line_id", 0)))
                else:
                    break

            included_lids = pre_lids + in_lids
            for lid in included_lids:
                meta_ids.add(lid)

            if included_lids:
                log_items.append(
                    {
                        "kind": "book_metadata_additional_toc",
                        "source": "later_toc_section_headings_with_empty_fragments",
                        "page_number_start": sp.get("page_number_start"),
                        "page_number_end": sp.get("page_number_end"),
                        "start_line_id": s_lid,
                        "end_line_id_inclusive": e_lid,
                        "pre_span_heading_line_ids": pre_lids,
                        "in_span_heading_line_ids": in_lids,
                        "heading_line_ids": included_lids,
                        "count": len(included_lids),
                    }
                )

    return meta_ids, log_items

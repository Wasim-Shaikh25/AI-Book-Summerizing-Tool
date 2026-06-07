"""Stage 15b — wire doubted-section resolver into the pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from src.shared.models import FinalHeading, NormalizedLine
from src.modules.structure.final_structuring.doubted_section_resolver import resolve_doubted_section


def lines_to_resolver_dicts(
    lines: List[NormalizedLine],
    layout_by_line_id: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if lid is None:
            continue
        layout = layout_by_line_id.get(int(lid), {})
        out.append(
            {
                "line_id": int(lid),
                "text": getattr(ln, "text", "") or "",
                "page_number": getattr(ln, "page_number", None) or layout.get("page_number"),
                "is_bold": bool(getattr(ln, "is_bold", False)),
                "font_size": getattr(ln, "font_size", layout.get("font_size")),
            }
        )
    return out


def _first_toc_section_start(det_section_log: List[Dict[str, Any]]) -> Optional[int]:
    for row in det_section_log:
        if row.get("kind") == "toc_section_span":
            start = row.get("line_id_start") or row.get("start_line_id")
            if start is not None:
                return int(start)
    return None


def _confirmed_heading_texts(
    headings: List[FinalHeading],
    doubted_ids: Set[int],
) -> Set[str]:
    texts: Set[str] = set()
    for h in headings:
        lid = getattr(h, "line_id", None)
        if isinstance(lid, int) and lid in doubted_ids:
            continue
        t = (getattr(h, "text", "") or "").strip()
        if t:
            texts.add(t)
    return texts


def _confirmed_sets(
    headings: List[FinalHeading],
    lines: List[NormalizedLine],
    toc_section_line_ids: Set[int],
    doubted_ids: Set[int],
    first_toc_page: int,
) -> Tuple[Set[int], Set[int], Set[int]]:
    heading_line_ids: Set[int] = set()
    for h in headings:
        lid = getattr(h, "line_id", None)
        if isinstance(lid, int):
            heading_line_ids.add(lid)

    content_ids: Set[int] = set()
    toc_ids: Set[int] = set()
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if not isinstance(lid, int) or lid in doubted_ids:
            continue
        pg = getattr(ln, "page_number", None) or 0
        if lid in toc_section_line_ids:
            toc_ids.add(lid)
        elif pg > first_toc_page:
            content_ids.add(lid)
    return heading_line_ids, content_ids, toc_ids


def apply_resolution_to_headings(
    headings: List[FinalHeading],
    segments: List[Dict[str, Any]],
) -> Tuple[Set[int], Set[int]]:
    """Return (metadata_line_ids, toc_line_ids) derived from segment labels."""
    metadata_ids: Set[int] = set()
    toc_ids: Set[int] = set()
    heading_by_line = {
        int(getattr(h, "line_id")): h
        for h in headings
        if isinstance(getattr(h, "line_id", None), int)
    }

    for seg in segments:
        line_ids = [int(x) for x in (seg.get("line_ids") or [])]
        label = str(seg.get("resolved_as") or "")
        if label == "metadata":
            metadata_ids.update(line_ids)
        elif label == "toc":
            toc_ids.update(line_ids)
            for lid in line_ids:
                h = heading_by_line.get(lid)
                if h is not None:
                    h.is_toc = True
        elif label == "real_content":
            for lid in line_ids:
                h = heading_by_line.get(lid)
                if h is not None:
                    h.is_toc = False
                    h.in_toc_section = False

        if seg.get("demote_heading"):
            hid = seg.get("heading_line_id")
            if isinstance(hid, int) and hid in heading_by_line:
                heading_by_line[hid].level = 0

    return metadata_ids, toc_ids


def run_stage_15b_if_doubted(
    *,
    lines: List[NormalizedLine],
    headings: List[FinalHeading],
    layout_by_line_id: Dict[int, Dict[str, Any]],
    doubted_body_ids: Set[int],
    doubted_toc_ids: Set[int],
    first_toc_page: int,
    det_section_log: List[Dict[str, Any]],
    toc_section_line_ids: Set[int],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Set[int]]:
    """
    Run Stage 15b when doubted lines exist.

    Returns (segment_results, revalidation_audits, book_metadata_line_ids).
    """
    doubted_ids = sorted(doubted_body_ids | doubted_toc_ids)
    if not doubted_ids:
        return [], [], set()

    all_lines = lines_to_resolver_dicts(lines, layout_by_line_id)
    doubted_set = set(doubted_ids)
    heading_line_ids, content_ids, confirmed_toc_ids = _confirmed_sets(
        headings,
        lines,
        toc_section_line_ids,
        doubted_set,
        first_toc_page,
    )
    confirmed_texts = _confirmed_heading_texts(headings, doubted_set)

    segments, audits = resolve_doubted_section(
        doubted_ids,
        all_lines,
        heading_line_ids & doubted_set,
        confirmed_texts,
        content_ids,
        confirmed_toc_ids,
        first_toc_page=first_toc_page,
        first_toc_section_start_line_id=_first_toc_section_start(det_section_log),
        doubted_toc_line_ids=doubted_toc_ids,
    )

    metadata_ids, _toc_ids = apply_resolution_to_headings(headings, segments)
    return segments, audits, metadata_ids

"""
PDF visualization helpers (debug-only).

This module is used by `src/debug/run_toc_trace.py --visualize`.

It generates a simple, color-marked PDF that highlights:
- noise lines (from 02_noise_filter.json)
- final headings (from 09_final_headings.json)
- fragments (from 07_fragments.json)
- book document metadata (first TOC section, non-noise lines from 11_book_metadata.json, amber)
- deterministic TOC section lines (`toc_section_span` in 10_deterministic_toc.json, else `is_toc`, purple)
- legacy LLM TOC hints (from toc.json / 05_llm_toc_classification.json when present, orange)

Implementation notes:
- This is intentionally "best effort": if any optional dependency is missing
  (e.g. PyMuPDF), the caller will catch and report the error.
- We try to avoid making assumptions about exact JSON schema beyond keys
  that are already produced by PipelineLogger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True, slots=True)
class _LineBox:
    line_id: int
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_items(payload: dict) -> Iterable[dict]:
    """
    PipelineLogger envelopes most stages as: {"stage": "...", "items": [...]}.

    Some debug stages may have items as a dict:
      {"items": {"toc_blocks": [...], "metadata": {...}, "highlight_ranges": [...]}}

    In that case, callers should use `_get_items_dict`.
    """
    items = payload.get("items")
    if isinstance(items, list):
        return items
    return []


def _get_items_dict(payload: dict) -> dict:
    items = payload.get("items")
    return items if isinstance(items, dict) else {}


def _index_layout_boxes(layout_payload: dict) -> Dict[int, _LineBox]:
    """
    Index line boxes by line_id.

    Expected layout payload item keys (best-effort):
      - line_id: int
      - page_number (1-based) OR page (0-based)
      - bbox: [x0,y0,x1,y1] OR x0,y0,x1,y1
    """
    out: Dict[int, _LineBox] = {}
    for it in _iter_items(layout_payload):
        if "line_id" not in it:
            continue
        line_id = int(it["line_id"])

        if "page_number" in it:
            page = int(it.get("page_number", 1)) - 1
        else:
            page = int(it.get("page", 0))

        if "bbox" in it and isinstance(it["bbox"], list) and len(it["bbox"]) == 4:
            x0, y0, x1, y1 = it["bbox"]
        else:
            x0 = it.get("x0")
            y0 = it.get("y0")
            x1 = it.get("x1")
            y1 = it.get("y1")
            if None in (x0, y0, x1, y1):
                continue

        if float(x0) == 0.0 and float(y0) == 0.0 and float(x1) == 0.0 and float(y1) == 0.0:
            continue

        out[line_id] = _LineBox(
            line_id=line_id,
            page=page,
            x0=float(x0),
            y0=float(y0),
            x1=float(x1),
            y1=float(y1),
        )
    return out


def _collect_noise_line_ids(noise_payload: dict) -> List[int]:
    ids: List[int] = []
    for it in _iter_items(noise_payload):
        if "line_id" in it:
            ids.append(int(it["line_id"]))
    return ids


def _collect_heading_line_ids(final_headings_payload: dict) -> List[int]:
    ids: List[int] = []
    for it in _iter_items(final_headings_payload):
        if "line_id" in it:
            ids.append(int(it["line_id"]))
        else:
            s = it.get("start_line")
            e = it.get("end_line")
            if s is not None and e is not None:
                ids.extend(list(range(int(s), int(e) + 1)))
    return ids


# Pastel palette for alternating fragment colors (RGB 0-1)
_FRAGMENT_PALETTE: List[Tuple[float, float, float]] = [
    (0.55, 0.85, 1.00),  # sky blue
    (0.65, 1.00, 0.75),  # mint green
    (1.00, 0.92, 0.55),  # soft yellow
    (1.00, 0.75, 0.85),  # blush pink
    (0.80, 0.70, 1.00),  # lavender
    (0.70, 1.00, 0.95),  # aqua
    (1.00, 0.80, 0.60),  # peach
    (0.85, 0.85, 0.85),  # light gray
]


def _collect_fragments_ordered(fragments_payload: dict) -> List[Tuple[int, int]]:
    """Return sorted list of (start_line, end_line) per fragment."""
    pairs: List[Tuple[int, int]] = []
    for it in _iter_items(fragments_payload):
        s = it.get("start_line")
        e = it.get("end_line")
        if s is None or e is None:
            continue
        s_i, e_i = int(s), int(e)
        if e_i >= s_i:
            pairs.append((s_i, e_i))
    pairs.sort()
    return pairs


def _draw_fragments_colored(
    doc,
    fragments: List[Tuple[int, int]],
    line_boxes: Dict[int, "_LineBox"],
    claimed: Set[int],
) -> None:
    """Draw each fragment body line-by-line in a cycling pastel color so section
    boundaries are visible without creating large merged blocks."""
    import fitz  # type: ignore

    for frag_idx, (s, e) in enumerate(fragments):
        color = _FRAGMENT_PALETTE[frag_idx % len(_FRAGMENT_PALETTE)]
        for lid in range(s, e + 1):
            if lid in claimed or lid not in line_boxes:
                continue
            b = line_boxes[lid]
            if b.page < 0 or b.page >= len(doc):
                continue
            rect = fitz.Rect(b.x0, b.y0, b.x1, b.y1)
            doc[b.page].draw_rect(
                rect,
                color=color,
                fill=color,
                overlay=True,
                width=0.3,
                fill_opacity=0.10,
                stroke_opacity=0.20,
            )


def _collect_toc_line_ids(toc_payload: dict) -> List[int]:
    ids: List[int] = []
    for it in _iter_items(toc_payload):
        if "line_id" in it:
            ids.append(int(it["line_id"]))
        else:
            s = it.get("start_line")
            e = it.get("end_line")
            if s is not None and e is not None:
                ids.extend(list(range(int(s), int(e) + 1)))
    return ids


def _draw_boxes(
    doc,
    boxes: Iterable[_LineBox],
    *,
    stroke_rgb: Tuple[float, float, float],
    fill_rgb: Optional[Tuple[float, float, float]] = None,
    opacity: float = 0.25,
    width: float = 0.5,
) -> None:
    import fitz  # type: ignore

    stroke = stroke_rgb
    fill = fill_rgb

    for b in boxes:
        if b.page < 0 or b.page >= len(doc):
            continue
        page = doc[b.page]
        rect = fitz.Rect(b.x0, b.y0, b.x1, b.y1)
        page.draw_rect(
            rect,
            color=stroke,
            fill=fill,
            overlay=True,
            width=width,
            fill_opacity=opacity if fill is not None else 0,
            stroke_opacity=opacity,
        )


def _draw_visual_elements(
    doc,
    elements: List[dict],
    kind: str,
    *,
    stroke_rgb: Tuple[float, float, float],
    fill_rgb: Tuple[float, float, float],
    opacity: float = 0.18,
    width: float = 1.2,
) -> None:
    """Draw bounding boxes for tables/images/diagrams directly by page number + bbox."""
    import fitz  # type: ignore

    for el in elements:
        if not isinstance(el, dict) or el.get("kind") != kind:
            continue
        page_num = el.get("page_number")
        bbox = el.get("bbox")
        if page_num is None or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        page_idx = int(page_num) - 1
        if page_idx < 0 or page_idx >= len(doc):
            continue
        try:
            rect = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        except Exception:
            continue
        doc[page_idx].draw_rect(
            rect,
            color=stroke_rgb,
            fill=fill_rgb,
            overlay=True,
            width=width,
            fill_opacity=opacity,
            stroke_opacity=min(opacity * 2.0, 1.0),
        )


def _collect_toc_section_span_line_ids(det_toc_payload: dict) -> Set[int]:
    """Line IDs inside `toc_section_span` items (prefers explicit `line_ids`)."""
    ids: Set[int] = set()
    for it in _iter_items(det_toc_payload):
        if not isinstance(it, dict) or it.get("kind") != "toc_section_span":
            continue
        raw = it.get("line_ids")
        if isinstance(raw, list) and raw:
            for x in raw:
                try:
                    ids.add(int(x))
                except (TypeError, ValueError):
                    continue
            continue
        s = it.get("start_line_id")
        e = it.get("end_line_id_inclusive")
        if s is None or e is None:
            continue
        try:
            si, ei = int(s), int(e)
        except (TypeError, ValueError):
            continue
        if ei < si:
            continue
        ids.update(range(si, ei + 1))
    return ids


def _collect_book_metadata_line_ids(
    book_meta_payload: dict,
    noise_payload: dict,
    layout_payload: dict,
) -> Set[int]:
    """
    Same rule as `book_metadata_from_first_toc_section`: optional document prefix
    range plus first TOC section range, minus noise.
    """
    noise_ids = set(_collect_noise_line_ids(noise_payload))
    ids: Set[int] = set()

    def _add_range(lo: int, hi: int) -> None:
        if hi < lo:
            return
        for x in _iter_items(layout_payload):
            if not isinstance(x, dict) or "line_id" not in x:
                continue
            try:
                lid = int(x["line_id"])
            except (TypeError, ValueError):
                continue
            if lid < lo or lid > hi:
                continue
            if lid in noise_ids:
                continue
            ids.add(lid)

    for it in _iter_items(book_meta_payload):
        if not isinstance(it, dict):
            continue
        kind = it.get("kind")
        if kind == "book_metadata_first_toc":
            ps = it.get("document_prefix_start_line_id")
            pe = it.get("document_prefix_end_line_id_inclusive")
            if ps is not None and pe is not None:
                try:
                    _add_range(int(ps), int(pe))
                except (TypeError, ValueError):
                    pass

            ss = it.get("first_toc_section_start_line_id")
            se = it.get("first_toc_section_end_line_id_inclusive")
            if ss is None:
                ss = it.get("start_line_id")
            if se is None:
                se = it.get("end_line_id_inclusive")
            if ss is not None and se is not None:
                try:
                    _add_range(int(ss), int(se))
                except (TypeError, ValueError):
                    pass
        elif kind == "book_metadata_additional_toc":
            # Later mini-TOC metadata: explicit heading_line_ids list
            lids = it.get("heading_line_ids")
            if isinstance(lids, list):
                for x in lids:
                    try:
                        xi = int(x)
                    except (TypeError, ValueError):
                        continue
                    # Only add if not noise
                    for ly in _iter_items(layout_payload):
                        if not isinstance(ly, dict) or ly.get("line_id") != xi:
                            continue
                        # find in noise set
                        if xi not in noise_ids:
                            ids.add(xi)
                        break
    return ids


def _collect_is_toc_line_ids(final_headings_payload: dict) -> Set[int]:
    """Fallback: line IDs for headings marked `is_toc` (TOC seeds only)."""
    ids: Set[int] = set()
    for it in _iter_items(final_headings_payload):
        if not isinstance(it, dict):
            continue
        if it.get("is_toc") is not True:
            continue
        lid = it.get("line_id")
        if lid is None:
            continue
        try:
            ids.add(int(lid))
        except (TypeError, ValueError):
            continue
    return ids


def _resolve_toc_payload(run: Path) -> dict:
    """
    TOC line highlights are optional: production runs may skip LLM TOC stages.

    Prefer legacy debug filenames, then the whitelisted pipeline stage log.
    """
    candidates = [
        run / "toc.json",
        run.parent / "toc.json",
        run / "05b_toc_local_detection.json",
        run / "05_llm_toc_classification.json",
    ]
    for p in candidates:
        if p.exists():
            return _load_json(p)
    return {"stage": "toc_overlay_skipped", "items": []}


def visualize_run(*, pdf_path: str, run_dir: str) -> Path:
    """
    Create a visualization PDF for a previously generated run directory.

    Output: <run_dir>/visualization.pdf
    """
    run = Path(run_dir)
    layout_path = run / "01_layout_lines.json"
    noise_path = run / "02_noise_filter.json"
    fragments_path = run / "07_fragments.json"
    final_headings_path = run / "09_final_headings.json"

    if not layout_path.exists():
        raise FileNotFoundError(f"Missing {layout_path}")
    if not noise_path.exists():
        raise FileNotFoundError(f"Missing {noise_path}")
    if not fragments_path.exists():
        raise FileNotFoundError(f"Missing {fragments_path}")
    if not final_headings_path.exists():
        raise FileNotFoundError(f"Missing {final_headings_path}")

    layout = _load_json(layout_path)
    noise = _load_json(noise_path)
    fragments = _load_json(fragments_path)
    final_headings = _load_json(final_headings_path)
    toc_source = _resolve_toc_payload(run)

    det_toc_path = run / "10_deterministic_toc.json"
    det_toc_ids: Set[int] = set()
    if det_toc_path.exists():
        det_toc_ids = _collect_toc_section_span_line_ids(_load_json(det_toc_path))
    if not det_toc_ids:
        det_toc_ids = _collect_is_toc_line_ids(final_headings)

    book_meta_path = run / "11_book_metadata.json"
    book_meta_ids: Set[int] = set()
    if book_meta_path.exists():
        book_meta_ids = _collect_book_metadata_line_ids(_load_json(book_meta_path), noise, layout)

    doubted_body_ids: Set[int] = set()
    doubted_toc_ids: Set[int] = set()
    doubted_path = run / "14_doubted_sections.json"
    if doubted_path.exists():
        dp = _load_json(doubted_path)
        _di = dp.get("items")
        _d = _di if isinstance(_di, dict) else (dp if isinstance(dp, dict) else {})
        doubted_body_ids = set(int(x) for x in (_d.get("doubted_body_line_ids") or []))
        doubted_toc_ids  = set(int(x) for x in (_d.get("doubted_toc_line_ids")  or []))

    visual_elements_path = run / "13_visual_elements.json"
    visual_elements: List[dict] = []
    if visual_elements_path.exists():
        ve_payload = _load_json(visual_elements_path)
        raw = ve_payload.get("items") if isinstance(ve_payload, dict) else ve_payload
        if isinstance(raw, list):
            visual_elements = raw

    line_boxes = _index_layout_boxes(layout)

    noise_ids = set(_collect_noise_line_ids(noise))
    heading_ids = set(_collect_heading_line_ids(final_headings))
    fragment_pairs = _collect_fragments_ordered(fragments)
    fragment_ids = set(lid for s, e in fragment_pairs for lid in range(s, e + 1))
    toc_ids = set(_collect_toc_line_ids(toc_source))

    # Priority deduplication: each line_id gets exactly ONE color layer.
    # Higher priority layers claim their ids first; lower layers skip already-claimed ids.
    _claimed: Set[int] = set()

    def _exclusive(ids: Set[int]) -> List[_LineBox]:
        result = [line_boxes[i] for i in ids if i in line_boxes and i not in _claimed]
        _claimed.update(ids)
        return result

    boxes_noise          = _exclusive(noise_ids)
    boxes_doubted_toc    = _exclusive(doubted_toc_ids)
    boxes_det_toc        = _exclusive(det_toc_ids)
    boxes_book_meta      = _exclusive(book_meta_ids)
    boxes_toc_llm        = _exclusive(toc_ids)
    boxes_heading        = _exclusive(heading_ids)
    boxes_doubted_body   = _exclusive(doubted_body_ids)
    # fragments drawn separately with per-fragment colors; still claim their ids
    _claimed.update(fragment_ids)

    import fitz  # type: ignore

    doc = fitz.open(pdf_path)
    try:
        # Fragment coloring disabled per user request — body text left plain white
        # _draw_fragments_colored(doc, fragment_pairs, line_boxes, set(_claimed))
        # Doubted body lines — coral/salmon
        _draw_boxes(doc, boxes_doubted_body,
                    stroke_rgb=(0.95, 0.35, 0.25), fill_rgb=(0.95, 0.35, 0.25),
                    opacity=0.18, width=0.9)
        # Doubted TOC lines — amber-orange (distinct from metadata gold)
        _draw_boxes(doc, boxes_doubted_toc,
                    stroke_rgb=(0.95, 0.60, 0.10), fill_rgb=(0.95, 0.60, 0.10),
                    opacity=0.20, width=1.0)
        _draw_boxes(
            doc,
            boxes_book_meta,
            stroke_rgb=(0.92, 0.68, 0.08),
            fill_rgb=(0.92, 0.68, 0.08),
            opacity=0.16,
            width=0.75,
        )
        _draw_boxes(
            doc,
            boxes_det_toc,
            stroke_rgb=(0.55, 0.15, 0.85),
            fill_rgb=(0.55, 0.15, 0.85),
            opacity=0.14,
            width=0.85,
        )
        _draw_boxes(doc, boxes_heading, stroke_rgb=(0.2, 0.8, 0.2), fill_rgb=(0.2, 0.8, 0.2), opacity=0.16, width=0.7)
        _draw_boxes(doc, boxes_toc_llm, stroke_rgb=(0.95, 0.45, 0.1), fill_rgb=(0.95, 0.45, 0.1), opacity=0.22, width=0.9)
        _draw_boxes(doc, boxes_noise, stroke_rgb=(0.8, 0.2, 0.2), fill_rgb=(0.8, 0.2, 0.2), opacity=0.20, width=0.7)

        # Visual elements: drawn directly by page+bbox (not line_id)
        # Tables  — teal border
        _draw_visual_elements(doc, visual_elements, "table",
                              stroke_rgb=(0.0, 0.6, 0.6), fill_rgb=(0.0, 0.8, 0.8), opacity=0.12, width=1.5)
        # Images  — sky blue border
        _draw_visual_elements(doc, visual_elements, "image",
                              stroke_rgb=(0.1, 0.45, 0.9), fill_rgb=(0.3, 0.6, 1.0), opacity=0.14, width=1.2)
        # Diagrams — lavender border (now with text extraction check to reduce false positives)
        _draw_visual_elements(doc, visual_elements, "diagram",
                      stroke_rgb=(0.5, 0.2, 0.8), fill_rgb=(0.7, 0.5, 1.0), opacity=0.10, width=1.0)

        output_path = run / "visualization.pdf"
        doc.save(str(output_path))
        return output_path
    finally:
        doc.close()

"""
PDF visualization helpers (debug-only).

This module is used by `src/debug/run_toc_trace.py --visualize`.

It generates a simple, color-marked PDF that highlights:
- noise lines (from 02_noise_filter.json)
- final headings (from 09_final_headings.json)
- fragments (from 07_fragments.json)

Implementation notes:
- This is intentionally "best effort": if any optional dependency is missing
  (e.g. PyMuPDF), the caller will catch and report the error.
- We try to avoid making assumptions about exact JSON schema beyond keys that
  are already produced by PipelineLogger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


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
    PipelineLogger envelopes most stages as: {"stage": "...", "items": [...]}

    Some debug stages (e.g. 05b_toc_local_detection.json) have items as a dict:
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
      - bbox: [x0,y0,x1,y1]  OR x0,y0,x1,y1
    """
    out: Dict[int, _LineBox] = {}
    for it in _iter_items(layout_payload):
        if "line_id" not in it:
            continue
        line_id = int(it["line_id"])

        # In our pipeline logs this is `page_number` and is 1-based.
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
                # Can't draw without a bounding box.
                continue

        # Many lines may have zero bbox in the logs; skip them (nothing to draw).
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
        # 02_noise_filter.json payload is already "noise decisions"; it may not carry is_noise=True.
        # Treat all listed line_ids as noise.
        if "line_id" in it:
            ids.append(int(it["line_id"]))
    return ids


def _collect_heading_line_ids(final_headings_payload: dict) -> List[int]:
    ids: List[int] = []
    for it in _iter_items(final_headings_payload):
        # 09_final_headings.json items should have line_id and/or start_line/end_line.
        if "line_id" in it:
            ids.append(int(it["line_id"]))
        else:
            # Fallback: mark the heading range.
            s = it.get("start_line")
            e = it.get("end_line")
            if s is not None and e is not None:
                ids.extend(list(range(int(s), int(e) + 1)))
    return ids


def _collect_fragment_line_ids(fragments_payload: dict) -> List[int]:
    ids: List[int] = []
    for it in _iter_items(fragments_payload):
        s = it.get("start_line")
        e = it.get("end_line")
        if s is None or e is None:
            continue
        s_i = int(s)
        e_i = int(e)
        if e_i < s_i:
            continue
        ids.extend(list(range(s_i, e_i + 1)))
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
    # Requires PyMuPDF (fitz)
    import fitz  # type: ignore

    # PyMuPDF expects color tuples in 0..1 floats, not named colors.
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
    toc_local_path = run / "05b_toc_local_detection.json"

    if not layout_path.exists():
        raise FileNotFoundError(f"Missing {layout_path}")
    if not noise_path.exists():
        raise FileNotFoundError(f"Missing {noise_path}")
    if not fragments_path.exists():
        raise FileNotFoundError(f"Missing {fragments_path}")
    if not final_headings_path.exists():
        raise FileNotFoundError(f"Missing {final_headings_path}")
    if not toc_local_path.exists():
        raise FileNotFoundError(f"Missing {toc_local_path}")

    layout = _load_json(layout_path)
    noise = _load_json(noise_path)
    fragments = _load_json(fragments_path)
    final_headings = _load_json(final_headings_path)
    toc_local = _load_json(toc_local_path)

    line_boxes = _index_layout_boxes(layout)

    noise_ids = set(_collect_noise_line_ids(noise))
    heading_ids = set(_collect_heading_line_ids(final_headings))
    fragment_ids = set(_collect_fragment_line_ids(fragments))

    # TOC + Metadata ranges are emitted by local TOC detector as highlight_ranges.
    toc_ids: set[int] = set()
    meta_ids: set[int] = set()

    toc_items = _get_items_dict(toc_local)
    highlight_ranges = toc_items.get("highlight_ranges")
    if isinstance(highlight_ranges, list):
        for hr in highlight_ranges:
            if not isinstance(hr, dict):
                continue
            label = (hr.get("label") or "").upper()
            s = hr.get("start_line_id")
            e = hr.get("end_line_id")
            if s is None or e is None:
                continue
            ids = set(range(int(s), int(e) + 1))
            if label == "TOC":
                toc_ids |= ids
            elif label == "METADATA":
                meta_ids |= ids

    # Convert to boxes (skip if we don't have bbox for that line_id).
    noise_boxes = [line_boxes[i] for i in noise_ids if i in line_boxes]
    heading_boxes = [line_boxes[i] for i in heading_ids if i in line_boxes]
    fragment_boxes = [line_boxes[i] for i in fragment_ids if i in line_boxes]
    toc_boxes = [line_boxes[i] for i in toc_ids if i in line_boxes]
    meta_boxes = [line_boxes[i] for i in meta_ids if i in line_boxes]

    import fitz  # type: ignore

    doc = fitz.open(pdf_path)

    # Draw order: fragments (light blue), metadata (purple), noise (red), headings (green), TOC (yellow ON TOP)
    # NOTE: TOC lines often overlap with "final headings". If headings are drawn last, TOC looks green.
    _draw_boxes(doc, fragment_boxes, stroke_rgb=(0.2, 0.4, 1.0), fill_rgb=(0.2, 0.4, 1.0), opacity=0.12, width=0.3)
    _draw_boxes(doc, meta_boxes, stroke_rgb=(0.60, 0.35, 0.20), fill_rgb=(0.60, 0.35, 0.20), opacity=0.16, width=0.8)
    _draw_boxes(doc, noise_boxes, stroke_rgb=(1.0, 0.2, 0.2), fill_rgb=(1.0, 0.2, 0.2), opacity=0.22, width=0.4)
    _draw_boxes(doc, heading_boxes, stroke_rgb=(0.2, 0.8, 0.2), fill_rgb=(0.2, 0.8, 0.2), opacity=0.18, width=0.6)
    _draw_boxes(doc, toc_boxes, stroke_rgb=(1.0, 0.95, 0.0), fill_rgb=(1.0, 0.95, 0.0), opacity=0.35, width=1.2)

    out_path = run / "visualization.pdf"
    doc.save(out_path.as_posix())
    doc.close()
    return out_path

from __future__ import annotations

from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import NormalizedLine


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _safe_median(values: List[float], default: float = 0.0) -> float:
    vals = [v for v in values if v is not None]
    if not vals:
        return default
    try:
        return float(median(vals))
    except Exception:
        return default


def _is_bold_from_flags(flags: int) -> bool:
    # PyMuPDF span flags are bitfields; 16 is commonly used for "bold".
    # Keep permissive: treat any flag containing 16 as bold.
    try:
        return bool(flags & 16)
    except Exception:
        return False


def _line_has_link(line: Dict[str, Any]) -> bool:
    # PyMuPDF dict doesn't directly mark links in text spans.
    # We keep this deterministic false for now; can be enhanced by inspecting page.get_links()
    # and intersecting with line bbox later.
    return False


def _extract_lines_from_page_dict(
    *,
    page_dict: Dict[str, Any],
    page_number: int,
    line_id_start: int,
) -> Tuple[List[NormalizedLine], int]:
    """
    Extracts normalized lines from a single PyMuPDF page.get_text("dict") output.
    Deterministic ordering: iterate blocks->lines in the returned order.
    """
    blocks = page_dict.get("blocks") or []
    page_w = float(page_dict.get("width") or 0.0)
    page_h = float(page_dict.get("height") or 0.0)

    # First pass: collect raw line items
    raw_items: List[Dict[str, Any]] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") != 0:
            # type 0 = text, skip images etc.
            continue
        for ln in b.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            spans = ln.get("spans") or []
            if not spans:
                continue

            # Compose line text in span order (no trimming beyond exact concatenation)
            text_parts: List[str] = []
            sizes: List[float] = []
            bold_any = False
            x0s: List[float] = []
            x1s: List[float] = []
            y0s: List[float] = []
            y1s: List[float] = []

            for sp in spans:
                if not isinstance(sp, dict):
                    continue
                t = sp.get("text")
                if t is None:
                    continue
                text_parts.append(str(t))
                try:
                    sizes.append(float(sp.get("size") or 0.0))
                except Exception:
                    sizes.append(0.0)
                bold_any = bold_any or _is_bold_from_flags(int(sp.get("flags") or 0))
                bbox = sp.get("bbox") or ln.get("bbox")
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    x0, y0, x1, y1 = bbox
                    try:
                        x0s.append(float(x0))
                        y0s.append(float(y0))
                        x1s.append(float(x1))
                        y1s.append(float(y1))
                    except Exception:
                        pass

            line_text = "".join(text_parts)

            # Line bbox from spans; fallback to line bbox
            if not x0s or not x1s or not y0s or not y1s:
                bbox = ln.get("bbox")
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    try:
                        x0s = [float(bbox[0])]
                        y0s = [float(bbox[1])]
                        x1s = [float(bbox[2])]
                        y1s = [float(bbox[3])]
                    except Exception:
                        x0s, y0s, x1s, y1s = [], [], [], []

            x0 = min(x0s) if x0s else 0.0
            x1 = max(x1s) if x1s else 0.0
            y0 = min(y0s) if y0s else 0.0
            y1 = max(y1s) if y1s else 0.0
            x_center = (x0 + x1) / 2.0
            y_pos = y0  # top of line

            font_size = _safe_median(sizes, default=0.0)
            raw_items.append(
                {
                    "text": line_text,
                    "y_pos": y_pos,
                    "x_center": x_center,
                    "font_size": font_size,
                    "is_bold": bool(bold_any),
                    "page_width": page_w,
                    "page_height": page_h,
                    "is_link": _line_has_link(ln),
                    "bbox": [x0, y0, x1, y1],
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "font_name": str(spans[0].get("font") or ""),
                    "is_italic": bool(int(spans[0].get("flags") or 0) & 2),
                }
            )

    # Second pass: compute vertical gaps (per page)
    # Use y_pos ordering to compute gap above.
    sorted_by_y = sorted(
        enumerate(raw_items),
        key=lambda t: (float(t[1].get("y_pos") or 0.0), t[0]),
    )
    prev_y: Optional[float] = None
    for _, item in sorted_by_y:
        y = float(item.get("y_pos") or 0.0)
        if prev_y is None:
            item["vertical_gap_above"] = 0.0
        else:
            gap = y - prev_y
            item["vertical_gap_above"] = float(gap) if gap > 0 else 0.0
        prev_y = y

    # Per-page medians for derived signals
    median_font = _safe_median([float(i.get("font_size") or 0.0) for i in raw_items], default=0.0)
    median_gap = _safe_median([float(i.get("vertical_gap_above") or 0.0) for i in raw_items], default=0.0)

    out: List[NormalizedLine] = []
    line_id = line_id_start
    for item in raw_items:
        page_width = float(item.get("page_width") or 0.0)
        x_center = float(item.get("x_center") or 0.0)

        centered = abs(x_center - (page_width / 2.0)) < (page_width * 0.1) if page_width else False
        font_size = float(item.get("font_size") or 0.0)
        vertical_gap_above = float(item.get("vertical_gap_above") or 0.0)

        large_font = font_size > median_font if median_font else False
        large_gap = vertical_gap_above > (median_gap * 1.8) if median_gap else False

        out.append(
            NormalizedLine(
                line_id=line_id,
                text=str(item.get("text") or ""),
                page_number=page_number,
                y_pos=float(item.get("y_pos") or 0.0),
                page_height=float(item.get("page_height") or 0.0),
                font_size=font_size,
                is_bold=bool(item.get("is_bold")),
                x_center=x_center,
                page_width=page_width,
                vertical_gap_above=vertical_gap_above,
                is_link=bool(item.get("is_link")),
                centered=centered,
                large_font=large_font,
                large_gap=large_gap,
            )
        )
        line_id += 1

    return out, line_id


def enrich_layout_from_pymupdf_pages(
    pages: List[Dict[str, Any]],
) -> List[NormalizedLine]:
    """
    Convert a list of page dicts (from PyMuPDF page.get_text('dict')) into enriched NormalizedLine list.
    """
    out: List[NormalizedLine] = []
    line_id = 0
    for idx, page_dict in enumerate(pages):
        page_number = int(page_dict.get("page_number") or (idx + 1))
        lines, line_id = _extract_lines_from_page_dict(
            page_dict=page_dict,
            page_number=page_number,
            line_id_start=line_id,
        )
        out.extend(lines)
    return out


def lines_to_log(lines: Iterable[NormalizedLine]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw_idx, ln in enumerate(lines):
        # Provide the exact schema required by 01_layout_lines.json.
        bbox = getattr(ln, "bbox", None)
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            # Derive a best-effort bbox from x_center and y_pos if not present.
            bbox = [0.0, _safe_float(getattr(ln, "y_pos", 0.0)), 0.0, _safe_float(getattr(ln, "y_pos", 0.0))]

        x0 = _safe_float(getattr(ln, "x0", bbox[0] if bbox else 0.0))
        y0 = _safe_float(getattr(ln, "y0", bbox[1] if bbox else 0.0))
        x1 = _safe_float(getattr(ln, "x1", bbox[2] if bbox else 0.0))
        y1 = _safe_float(getattr(ln, "y1", bbox[3] if bbox else 0.0))

        out.append(
            {
                "line_id": ln.line_id,
                "text": ln.text,
                "page_number": ln.page_number,
                "bbox": [x0, y0, x1, y1],
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "page_width": ln.page_width,
                "page_height": ln.page_height,
                "font_size": ln.font_size,
                "font_name": str(getattr(ln, "font_name", "")),
                "is_bold": ln.is_bold,
                "is_italic": bool(getattr(ln, "is_italic", False)),
                "x_center": ln.x_center,
                "centered": ln.centered,
                "vertical_gap_above": ln.vertical_gap_above,
                "large_gap": ln.large_gap,
                "large_font": ln.large_font,
                "is_link": ln.is_link,
                "is_table": False,
                "raw_line_index": raw_idx,
            }
        )
    return out

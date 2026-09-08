"""Docling ML layout parser → NormalizedLine adapter."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from src.shared.models import NormalizedLine

from ..layout_enrichment import finalize_line_layout_signals

logger = logging.getLogger(__name__)

_HEADING_LABELS = frozenset(
    {
        "title",
        "section_header",
        "document_index",
    }
)
_SKIP_LABELS = frozenset(
    {
        "page_header",
        "page_footer",
        "footnote",
    }
)
_TABLE_LABELS = frozenset({"table"})


def docling_import_error() -> Optional[str]:
    try:
        import docling  # noqa: F401
        from docling.document_converter import DocumentConverter  # noqa: F401

        return None
    except ImportError as exc:
        return str(exc)


def docling_available() -> bool:
    return docling_import_error() is None


def _label_str(item: Any) -> str:
    label = getattr(item, "label", None)
    if label is None:
        return "text"
    return str(getattr(label, "value", label)).lower()


def _item_text(item: Any) -> str:
    text = getattr(item, "text", None)
    if text:
        return str(text).strip()
    getter = getattr(item, "get_text", None)
    if callable(getter):
        return str(getter()).strip()
    return ""


def _prov_page_bbox(item: Any) -> Tuple[int, float, float, float, float, float, float]:
    """Return page_no, x0, y0, x1, y1, page_w, page_h."""
    prov = getattr(item, "prov", None) or []
    page_no = 1
    x0 = y0 = 0.0
    x1 = 595.0
    y1 = 842.0
    page_w = 595.0
    page_h = 842.0
    if not prov:
        return page_no, x0, y0, x1, y1, page_w, page_h

    p0 = prov[0]
    page_no = int(getattr(p0, "page_no", 1) or 1)
    bbox = getattr(p0, "bbox", None)
    if bbox is not None:
        x0 = float(getattr(bbox, "l", getattr(bbox, "x0", 0.0)) or 0.0)
        y0 = float(getattr(bbox, "t", getattr(bbox, "y0", 0.0)) or 0.0)
        x1 = float(getattr(bbox, "r", getattr(bbox, "x1", x0 + 1)) or x0 + 1)
        y1 = float(getattr(bbox, "b", getattr(bbox, "y1", y0 + 12)) or y0 + 12)
    return page_no, x0, y0, x1, y1, page_w, page_h


def _lines_from_docling_item(item: Any, *, label: str) -> List[str]:
    text = _item_text(item)
    if not text:
        return []
    if label in _TABLE_LABELS:
        return [text]
    parts = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return parts or [text]


def docling_items_to_normalized_lines(items: List[Any]) -> List[NormalizedLine]:
    """Convert pre-parsed Docling items to NormalizedLine (for tests)."""
    out: List[NormalizedLine] = []
    line_id = 0
    for item in items:
        label = _label_str(item)
        if label in _SKIP_LABELS:
            continue
        page_no, x0, y0, x1, y1, page_w, page_h = _prov_page_bbox(item)
        is_heading = label in _HEADING_LABELS
        is_table = label in _TABLE_LABELS
        source = f"docling:{label}" if is_table or is_heading else "docling"
        font_size = 14.0 if is_heading else 10.0
        for chunk in _lines_from_docling_item(item, label=label):
            out.append(
                NormalizedLine(
                    line_id=line_id,
                    text=chunk,
                    page_number=page_no,
                    y_pos=y0,
                    font_size=font_size,
                    page_height=page_h,
                    page_width=page_w,
                    x0=x0,
                    x1=x1,
                    y0=y0,
                    y1=y1,
                    x_center=(x0 + x1) / 2.0,
                    is_bold=is_heading,
                    is_centered=is_heading and label == "title",
                    large_font=is_heading,
                    source="table" if is_table else source,
                )
            )
            line_id += 1
    return finalize_line_layout_signals(out)


def extract_lines_docling(
    pdf_path: str,
    *,
    max_pages: int | None = None,
) -> List[NormalizedLine]:
    """Run Docling DocumentConverter and map to NormalizedLine list."""
    err = docling_import_error()
    if err:
        raise ImportError(
            "Docling is not installed. Install optional deps: "
            "pip install -r requirements-ml-layout.txt"
        ) from ImportError(err)

    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    doc = result.document

    items: List[Any] = []
    iterate = getattr(doc, "iterate_items", None)
    if callable(iterate):
        for entry in iterate():
            if isinstance(entry, tuple):
                items.append(entry[0])
            else:
                items.append(entry)
    else:
        items = list(getattr(doc, "texts", []) or [])

    lines = docling_items_to_normalized_lines(items)
    if max_pages and max_pages > 0:
        lines = [ln for ln in lines if (ln.page_number or 0) <= max_pages]
    logger.info("Docling layout: %d items -> %d lines", len(items), len(lines))
    return lines

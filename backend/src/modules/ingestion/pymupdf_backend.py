"""PyMuPDF + Tesseract OCR layout extraction (legacy signal path)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.shared.models import NormalizedLine

from .layout_enrichment import enrich_layout_from_pymupdf_pages
from .ocr_stage import apply_ocr_to_pages


def pymupdf_extract_pages_dict(pdf_path: str, *, max_pages: int | None = None) -> List[Dict[str, Any]]:
    """Extract PyMuPDF page dicts via page.get_text("dict")."""
    import fitz

    from src.shared import config

    limit = max(0, int(max_pages or 0))
    if limit <= 0:
        limit = int(config.PIPELINE_MAX_PAGES or 0)
    doc = fitz.open(pdf_path)
    pages: List[Dict[str, Any]] = []
    end = len(doc) if limit <= 0 else min(len(doc), limit)
    try:
        for i in range(end):
            page = doc.load_page(i)
            d = page.get_text("dict")
            d["page_number"] = i + 1
            try:
                rect = page.rect
                d["width"] = float(getattr(rect, "width", 0.0))
                d["height"] = float(getattr(rect, "height", 0.0))
            except Exception:
                d.setdefault("width", 0.0)
                d.setdefault("height", 0.0)
            pages.append(d)
    finally:
        doc.close()
    return pages


def extract_lines_pymupdf(
    pdf_path: str,
    *,
    max_pages: int | None = None,
    visual_elements: List[Dict[str, Any]] | None = None,
) -> Tuple[List[NormalizedLine], List[Dict[str, Any]]]:
    """PyMuPDF dict extract + optional OCR + layout enrichment."""
    from src.shared import config

    pages_dict = pymupdf_extract_pages_dict(pdf_path, max_pages=max_pages)
    visuals = list(visual_elements or [])

    pages_dict, ocr_log = apply_ocr_to_pages(
        pdf_path,
        pages_dict,
        visuals,
        enabled=bool(getattr(config, "OCR_ENABLED", True)),
        mode=str(getattr(config, "OCR_MODE", "auto")),
        split_two_up=bool(getattr(config, "OCR_SPLIT_TWO_UP", False)),
        min_text_chars=int(getattr(config, "OCR_MIN_TEXT_CHARS", 40) or 40),
        zoom=float(getattr(config, "OCR_ZOOM", 2.0) or 2.0),
        lang=str(getattr(config, "OCR_LANG", "eng") or "eng"),
        tesseract_cmd=str(getattr(config, "TESSERACT_CMD", "") or ""),
    )
    lines = enrich_layout_from_pymupdf_pages(pages_dict, visual_elements=visuals)
    return lines, ocr_log

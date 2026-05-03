from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF

from src.utils.pdf_reader import PDFReader
from src.utils.ocr_reader import OCRReader

from .layout_enrichment import enrich_layout_from_pymupdf_pages
from src.domain.document import NormalizedLine


def _pymupdf_extract_pages_dict(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract PyMuPDF page dicts via page.get_text("dict"), preserving page order.
    Adds explicit page_number for downstream stability.
    """
    doc = fitz.open(pdf_path)
    pages: List[Dict[str, Any]] = []
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            d = page.get_text("dict")
            # Include dimensions explicitly; some PyMuPDF versions include these already.
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


def extract_visual_elements(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract non-text visual elements from each page:
      - "table"  : detected via page.find_tables() (PyMuPDF >= 1.23)
      - "image"  : raster/vector image blocks (type=1 in get_text("dict"))
      - "diagram": significant clusters of drawing paths that are not tables/images

    Returns a list of {"kind", "page_number", "bbox": [x0,y0,x1,y1]} dicts.
    """
    doc = fitz.open(pdf_path)
    elements: List[Dict[str, Any]] = []
    try:
        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            page_num = page_idx + 1
            page_rect = page.rect
            page_area = float(page_rect.width * page_rect.height) or 1.0

            table_bboxes: List[List[float]] = []

            # --- Tables ---
            try:
                tf = page.find_tables()
                for tbl in (tf.tables if hasattr(tf, "tables") else []):
                    # Only real grids: require at least 2 rows and 2 columns.
                    # Single-row or single-column detections are usually indented
                    # lists or case-law paragraphs, not tables.
                    try:
                        n_rows = len(tbl.rows) if hasattr(tbl, "rows") else 0
                        n_cols = len(tbl.cols) if hasattr(tbl, "cols") else 0
                    except Exception:
                        n_rows = n_cols = 0
                    if n_rows < 2 or n_cols < 2:
                        continue
                    b = tbl.bbox
                    if b and len(b) == 4:
                        bbox = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
                        try:
                            raw_cells = tbl.extract()
                        except Exception:
                            raw_cells = None
                        cells: List[List[str]] = []
                        flat_text_parts: List[str] = []
                        if raw_cells:
                            for row in raw_cells:
                                cell_row = []
                                for cell in (row or []):
                                    cv = (cell or "").strip()
                                    cell_row.append(cv)
                                    if cv:
                                        flat_text_parts.append(cv)
                                cells.append(cell_row)
                        elements.append({
                            "kind": "table",
                            "page_number": page_num,
                            "bbox": bbox,
                            "cells": cells,
                            "text": "\n".join(flat_text_parts),
                        })
                        table_bboxes.append(bbox)
            except Exception:
                pass

            # --- Images (type=1 blocks in get_text("dict")) + targeted OCR ---
            image_bboxes: List[List[float]] = []
            _ocr = OCRReader()
            try:
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks") or []:
                    if not isinstance(block, dict) or block.get("type") != 1:
                        continue
                    b = block.get("bbox")
                    if b and len(b) == 4:
                        bbox = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                        img_area = w * h
                        if img_area < 0.001 * page_area:
                            continue
                        # If the region already has extractable text, it is NOT a raster image —
                        # it's a styled text block stored as type=1 (e.g. Word-exported PDFs).
                        # The text extraction pipeline already handles it; skip here.
                        try:
                            region_text = page.get_textbox(fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3]))
                        except Exception:
                            region_text = ""
                        if region_text.strip():
                            continue
                        # Skip OCR on full/near-full-page scans (likely scanned pages, not figures)
                        if img_area > 0.25 * page_area:
                            elements.append({"kind": "image", "page_number": page_num, "bbox": bbox, "text": ""})
                            image_bboxes.append(bbox)
                            continue
                        ocr_text = _ocr.extract_text_from_region(pdf_path, page_num, bbox)
                        elements.append({
                            "kind": "image",
                            "page_number": page_num,
                            "bbox": bbox,
                            "text": ocr_text,
                        })
                        image_bboxes.append(bbox)
            except Exception:
                pass

            # --- Diagrams (clusters of drawing paths not explained by tables/images) ---
            try:
                drawings = page.get_drawings()
                rects: List[Tuple[float, float, float, float]] = []
                for d in drawings:
                    r = d.get("rect")
                    if r is None:
                        continue
                    try:
                        x0, y0, x1, y1 = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                    except (TypeError, ValueError, IndexError):
                        continue
                    w, h = x1 - x0, y1 - y0
                    area = w * h
                    if area < 0.0005 * page_area or area > 0.85 * page_area:
                        continue
                    if w > 0 and h > 0 and min(w, h) / max(w, h) < 0.015:
                        continue
                    rects.append((x0, y0, x1, y1))

                if len(rects) >= 5:
                    ux0 = min(r[0] for r in rects)
                    uy0 = min(r[1] for r in rects)
                    ux1 = max(r[2] for r in rects)
                    uy1 = max(r[3] for r in rects)
                    union_area = (ux1 - ux0) * (uy1 - uy0)
                    if 0.01 * page_area <= union_area <= 0.80 * page_area:
                        overlaps_table = False
                        for tb in table_bboxes:
                            ix0 = max(ux0, tb[0]); iy0 = max(uy0, tb[1])
                            ix1 = min(ux1, tb[2]); iy1 = min(uy1, tb[3])
                            if ix1 > ix0 and iy1 > iy0:
                                overlap_area = (ix1 - ix0) * (iy1 - iy0)
                                if overlap_area > 0.3 * union_area:
                                    overlaps_table = True
                                    break
                        # Check if text can be extracted from this region
                        # If yes, it's likely styled text with drawing paths, not a pure diagram
                        has_extractable_text = False
                        try:
                            clip_rect = fitz.Rect(ux0, uy0, ux1, uy1)
                            text_in_region = page.get_text(clip=clip_rect, textpage=None).strip()
                            if text_in_region:
                                has_extractable_text = True
                        except Exception:
                            pass
                        if not overlaps_table and not has_extractable_text:
                            elements.append({
                                "kind": "diagram",
                                "page_number": page_num,
                                "bbox": [ux0, uy0, ux1, uy1],
                            })
            except Exception:
                pass

    finally:
        doc.close()
    return elements


def _title_from_path(pdf_path: str) -> str:
    """Derive a clean book title from the PDF filename (no OCR, no I/O)."""
    import re as _re
    base = Path(pdf_path).stem
    base = _re.sub(r'\[\d+-\d+\]', '', base)
    base = _re.sub(r'Notes\s*(MU)?\s*(New\s*syllabus)?\s*\d{4}\s*\d{2}\s*\d{2}', '', base, flags=_re.IGNORECASE)
    base = _re.sub(r'Notes\s*(\d{4}\s*\d{2}\s*\d{2})?', '', base, flags=_re.IGNORECASE)
    for word in ("Notes", "PDF", "final", "summary"):
        base = _re.sub(word, '', base, flags=_re.IGNORECASE)
    base = _re.sub(r'chapter\s*\d+', '', base, flags=_re.IGNORECASE)
    title = _re.sub(r'\s+', ' ', base).strip()
    return title if title else "Rewritten Book Notes"


def extract_pdf(pdf_path: str) -> Tuple[List[NormalizedLine], str, List[Dict[str, Any]]]:
    """
    Phase: robust extraction.

    Returns:
      (enriched_lines, book_title, visual_elements)

    - enriched_lines: NormalizedLines including image OCR lines (source='image_ocr')
      and table-tagged lines (source='table'), interleaved in reading order.
    - book_title: derived from the filename.
    - visual_elements: list of {kind, page_number, bbox, text/cells} dicts.
    """
    book_title = _title_from_path(pdf_path)

    # Visual elements (tables with cells, images with OCR, diagrams)
    visual_elements = extract_visual_elements(pdf_path)

    # Layout: structured extraction with OCR injection and table tagging
    pages_dict = _pymupdf_extract_pages_dict(pdf_path)
    enriched_lines = enrich_layout_from_pymupdf_pages(pages_dict, visual_elements=visual_elements)

    return enriched_lines, book_title, visual_elements

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF

from src.utils.pdf_reader import PDFReader

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
                    b = tbl.bbox
                    if b and len(b) == 4:
                        bbox = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
                        elements.append({"kind": "table", "page_number": page_num, "bbox": bbox})
                        table_bboxes.append(bbox)
            except Exception:
                pass

            # --- Images (type=1 blocks in get_text("dict")) ---
            image_bboxes: List[List[float]] = []
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
                        if w * h < 0.001 * page_area:
                            continue
                        elements.append({"kind": "image", "page_number": page_num, "bbox": bbox})
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
                                if (ix1 - ix0) * (iy1 - iy0) > 0.5 * union_area:
                                    overlaps_table = True
                                    break
                        if not overlaps_table:
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


def extract_pdf(pdf_path: str) -> Tuple[List[NormalizedLine], str]:
    """
    Phase: robust extraction.

    Returns:
      (enriched_lines, book_title)

    - enriched_lines: List[NormalizedLine] with PyMuPDF-derived layout metadata.
    - book_title: reuses the existing filename-based extractor from PDFReader for compatibility.
    """
    # Title: keep existing behavior (filename-based) without changing logic.
    # Use a stable default folder, but still allow passing explicit paths anywhere in the repo.
    from src.config import PDF_FOLDER
    reader = PDFReader(pdf_folder=PDF_FOLDER)
    _pages_data, book_title = reader.read_all_pdfs(specific_file=pdf_path)

    # Layout: true structured extraction for universal pipeline
    pages_dict = _pymupdf_extract_pages_dict(pdf_path)
    enriched_lines = enrich_layout_from_pymupdf_pages(pages_dict)

    return enriched_lines, book_title

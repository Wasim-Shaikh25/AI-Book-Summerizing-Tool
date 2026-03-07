from __future__ import annotations

from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF

from src.utils.pdf_reader import PDFReader
from .layout_enrichment import enrich_layout_from_pymupdf_pages
from .models import NormalizedLine


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

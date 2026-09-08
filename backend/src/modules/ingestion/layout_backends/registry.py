"""Resolve and run ingestion layout backend."""

from __future__ import annotations

import logging
from typing import List, Tuple

from src.shared.models import NormalizedLine

from .auto_detect import pdf_likely_scanned
from .docling_adapter import docling_available, extract_lines_docling
from ..pymupdf_backend import extract_lines_pymupdf, pymupdf_extract_pages_dict

logger = logging.getLogger(__name__)


def resolve_layout_backend(
    pdf_path: str,
    *,
    pages_sample: list | None = None,
) -> str:
    """
    Choose layout backend: pymupdf | docling | auto.

    auto: use Docling when installed and PDF looks scanned; else PyMuPDF+OCR.
    """
    from src.shared import config

    mode = str(getattr(config, "INGESTION_LAYOUT_BACKEND", "auto") or "auto").strip().lower()
    if mode in {"pymupdf", "legacy", "signals"}:
        return "pymupdf"
    if mode == "docling":
        if docling_available():
            return "docling"
        logger.warning("INGESTION_LAYOUT_BACKEND=docling but Docling not installed; using pymupdf")
        return "pymupdf"

    if not docling_available():
        return "pymupdf"

    min_chars = int(getattr(config, "OCR_MIN_TEXT_CHARS", 40) or 40)
    if pages_sample is None:
        sample_limit = int(getattr(config, "INGESTION_LAYOUT_AUTO_SAMPLE_PAGES", 8) or 8)
        pages_sample = pymupdf_extract_pages_dict(pdf_path, max_pages=sample_limit)

    if pdf_likely_scanned(pages_sample, min_text_chars=min_chars):
        logger.info("Auto layout backend: docling (scan-like PDF detected)")
        return "docling"

    if bool(getattr(config, "INGESTION_LAYOUT_DOCLING_ALWAYS", False)) or mode == "ml":
        logger.info("Auto layout backend: docling (INGESTION_LAYOUT_DOCLING_ALWAYS)")
        return "docling"

    return "pymupdf"


def extract_layout_lines(
    pdf_path: str,
    *,
    max_pages: int | None = None,
    visual_elements: list | None = None,
) -> Tuple[List[NormalizedLine], str, dict]:
    """
    Extract NormalizedLines using the resolved backend.

    Returns (lines, backend_name, meta).
    """
    backend = resolve_layout_backend(pdf_path)
    meta: dict = {"backend": backend}

    if backend == "docling":
        try:
            lines = extract_lines_docling(pdf_path, max_pages=max_pages)
            meta["docling"] = True
            return lines, backend, meta
        except Exception as exc:
            logger.warning("Docling extraction failed (%s); falling back to pymupdf", exc)
            meta["docling_error"] = str(exc)
            backend = "pymupdf"

    lines, ocr_log = extract_lines_pymupdf(
        pdf_path,
        max_pages=max_pages,
        visual_elements=visual_elements,
    )
    meta["backend"] = "pymupdf"
    if ocr_log:
        meta["ocr_log"] = ocr_log
    return lines, backend, meta

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.utils.pdf_reader import PDFReader


def extract_pdf(pdf_path: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Phase: integration stabilization.

    Deterministic PDF extraction wrapper for the clean pipeline.

    Returns:
      (pages_data, book_title) exactly as produced by the existing PDFReader.
    """
    reader = PDFReader(pdf_folder="reference_files")
    return reader.read_all_pdfs(specific_file=pdf_path)

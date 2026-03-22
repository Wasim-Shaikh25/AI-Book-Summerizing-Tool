from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.ingestion.pdf_extractor import extract_pdf


@dataclass(frozen=True, slots=True)
class IngestedPdf:
    """Minimal ingestion result.

    Keeps ingestion independent from later stages. Later stages can decide what they need
    from the underlying PDF object (usually the text/lines produced by normalization).
    """

    pdf: Any
    page_count: int


def ingest_pdf(file_path: str) -> IngestedPdf:
    """Load a PDF document and return minimal metadata."""
    pdf = extract_pdf(file_path)
    page_count = int(getattr(pdf, "page_count", 0) or 0)
    return IngestedPdf(pdf=pdf, page_count=page_count)

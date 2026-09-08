"""Tests for PDF outline TOC supplement."""

from __future__ import annotations

from src.modules.ingestion.pdf_outline import supplement_toc_from_pdf_outline
from src.shared.models import FinalHeading, NormalizedLine


def test_supplement_skips_when_enough_seeds() -> None:
    lines = [NormalizedLine(line_id=1, text="Chapter 1", page_number=1)]
    headings = [FinalHeading(id="h1", text="Chapter 1", level=1, line_id=1)]
    seeds, log = supplement_toc_from_pdf_outline(
        "missing.pdf",
        lines,
        headings,
        {1, 2, 3},
    )
    assert seeds == {1, 2, 3}
    assert any(item.get("kind") == "pdf_outline_skip" for item in log)


def test_supplement_no_outline_entries() -> None:
    lines: list[NormalizedLine] = []
    headings: list[FinalHeading] = []
    seeds, log = supplement_toc_from_pdf_outline("missing.pdf", lines, headings, set())
    assert seeds == set()
    assert log

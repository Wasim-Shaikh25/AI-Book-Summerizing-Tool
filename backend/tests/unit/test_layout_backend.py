"""Tests for ML layout backend routing and Docling adapter."""

from __future__ import annotations

from types import SimpleNamespace

from src.modules.ingestion.layout_backends.auto_detect import pdf_likely_scanned
from src.modules.ingestion.layout_backends.docling_adapter import docling_items_to_normalized_lines
from src.modules.ingestion.layout_backends.registry import resolve_layout_backend


def test_pdf_likely_scanned_detects_low_text_pages() -> None:
    pages = [
        {"blocks": []},
        {"blocks": [{"type": 0, "lines": [{"spans": [{"text": "x"}]}]}]},
    ]
    assert pdf_likely_scanned(pages, min_text_chars=40, scan_ratio=0.5) is True


def test_docling_items_map_section_header_to_heading_signals() -> None:
    item = SimpleNamespace(
        label=SimpleNamespace(value="section_header"),
        text="MODULE 1: Environmental Law",
        prov=[
            SimpleNamespace(
                page_no=2,
                bbox=SimpleNamespace(l=10, t=20, r=300, b=40),
            )
        ],
    )
    lines = docling_items_to_normalized_lines([item])
    assert len(lines) == 1
    assert lines[0].is_bold is True
    assert lines[0].large_font is True
    assert "MODULE 1" in lines[0].text
    assert lines[0].source.startswith("docling")


def test_resolve_layout_backend_pymupdf_when_forced(monkeypatch) -> None:
    monkeypatch.setattr("src.shared.config.INGESTION_LAYOUT_BACKEND", "pymupdf")
    assert resolve_layout_backend("any.pdf") == "pymupdf"

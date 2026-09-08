"""Tests for export cover title resolution."""

from __future__ import annotations

from pathlib import Path

from src.modules.export.document_formatter import humanize_book_title, resolve_export_book_title


def test_humanize_book_title_strips_numeric_suffix() -> None:
    assert "Family Law" in humanize_book_title("family-law-43811769208")


def test_resolve_export_book_title_from_md_stem() -> None:
    md = Path("output/environmental-law-1--43748672008_2026-06-15_11-18-25.md")
    title = resolve_export_book_title(md_path=md)
    assert "Environmental" in title
    assert "bareact" not in title.lower()


def test_resolve_export_book_title_prefers_sidecar_pdf() -> None:
    title = resolve_export_book_title(
        sidecar_meta={"pdf": "constitutional-law-i-sem-ii-2022-23-1--43527772408.pdf"},
        md_path=Path("output/bareact-140_2026-06-15_12-13-57.md"),
    )
    assert "Constitutional" in title

"""Tests for universal document format style (LLM + Word typography)."""
from __future__ import annotations

from src.shared.document_format_style import (
    format_spec_summary,
    resolve_body_font,
    resolve_typography,
    universal_rewrite_format_addendum,
)


def test_default_font_is_times_new_roman(monkeypatch) -> None:
    monkeypatch.delenv("DOCX_FONT_FAMILY", raising=False)
    assert resolve_body_font() == "Times New Roman"


def test_typography_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DOCX_BODY_SIZE_PT", raising=False)
    typo = resolve_typography()
    assert typo.body_size_pt == 11
    assert typo.h1_size_pt == 20
    assert typo.h2_size_pt == 16
    assert typo.h3_size_pt == 13


def test_universal_addendum_mentions_hierarchy() -> None:
    text = universal_rewrite_format_addendum()
    assert "H1" in text or "#" in text
    assert "Times New Roman" in text
    assert "Key Points" in text


def test_format_spec_summary() -> None:
    assert "Times New Roman" in format_spec_summary()

"""Notes export style (book vs study)."""

from __future__ import annotations

import os

import pytest

from src.modules.generation.markdown_format_normalizer import prefer_paragraph_format
from src.modules.structure.section_consolidation import is_low_value_heading
from src.shared.notes_export_style import is_book_export_style, resolve_notes_export_style


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("book", "book"),
        ("textbook", "book"),
        ("prose", "book"),
        ("study", "study"),
        ("", "study"),
    ],
)
def test_resolve_notes_export_style(raw: str, expected: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTES_EXPORT_STYLE", raising=False)
    assert resolve_notes_export_style(raw or None) == expected


def test_prefer_paragraph_format_when_book(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "book")
    assert prefer_paragraph_format("") is True
    assert is_book_export_style() is True


def test_all_caps_heading_is_low_value() -> None:
    assert is_low_value_heading("OF OFFENCES AGAINST THE STATE") is True
    assert is_low_value_heading("CHAPTER VI") is True

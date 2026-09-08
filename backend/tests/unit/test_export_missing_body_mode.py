"""Tests for export missing-body handling."""

from __future__ import annotations

import os

import pytest

from src.modules.export.document_formatter import (
    chapter_blocks_from_hierarchy,
    resolve_export_missing_body_mode,
)


def _hierarchy() -> dict:
    return {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Intro",
                "sections": [
                    {
                        "section_id": "S1",
                        "heading": "First topic",
                        "page_number": 12,
                        "fragment": {},
                    }
                ],
            }
        ]
    }


def test_resolve_export_missing_body_mode_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXPORT_MISSING_BODY_MODE", raising=False)
    assert resolve_export_missing_body_mode() == "placeholder"


def test_placeholder_mode_preserves_section(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPORT_MISSING_BODY_MODE", "placeholder")
    blocks, _ = chapter_blocks_from_hierarchy(_hierarchy(), {})
    assert blocks
    assert "page 12" in blocks[0].lower()
    assert "S1" in blocks[0]


def test_skip_mode_drops_empty_section(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPORT_MISSING_BODY_MODE", "skip")
    blocks, _ = chapter_blocks_from_hierarchy(_hierarchy(), {})
    assert blocks == []


def test_fail_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPORT_MISSING_BODY_MODE", "fail")
    with pytest.raises(ValueError, match="S1"):
        chapter_blocks_from_hierarchy(_hierarchy(), {})

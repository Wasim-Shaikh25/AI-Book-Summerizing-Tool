"""Tests for export-time section display heading repair."""

from __future__ import annotations

from src.modules.structure.final_structuring.heading_title_engine import resolve_section_display_heading


def test_display_heading_repairs_currency_fragment() -> None:
    sec = {
        "heading": "Rs.10 lakh — 111 BNS.",
        "subheadings": [{"heading": "Fine for offence under BNS 111"}],
        "fragment": {"preview": "Whoever commits offence punishable with fine up to ten lakh rupees"},
        "page_number": 14,
    }
    out = resolve_section_display_heading(sec, chapter_heading="Classification of Offences", use_transformers=False)
    assert "Rs.10" not in out
    assert out


def test_display_heading_keeps_good_statute_title() -> None:
    sec = {"heading": "Section 106: Causing death by negligence.", "subheadings": [], "fragment": {}}
    out = resolve_section_display_heading(sec, use_transformers=False)
    assert "Section 106" in out

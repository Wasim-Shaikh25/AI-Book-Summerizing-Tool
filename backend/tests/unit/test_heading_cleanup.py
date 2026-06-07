"""Unit tests for stage 15f heading cleanup rules."""
from __future__ import annotations

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.final_structuring.heading_cleanup import (
    _rule_clean_heading,
    clean_heading_hierarchy,
)


def test_rule_clean_art_only() -> None:
    out = _rule_clean_heading("(Art. 21)")
    assert out == "Article 21"
    assert not is_weak_section_heading(out)


def test_rule_strip_number_prefix() -> None:
    out = _rule_clean_heading("1. Equality before the law (Art. 14)")
    assert out == "Equality before the law (Art. 14)"
    assert not is_weak_section_heading(out)


def test_rule_dedupe_chapters() -> None:
    hierarchy = {
        "meta": {},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "The Union Executive",
                "page_start": 72,
                "sections": [{"section_id": "S1", "heading": "President", "fragment": {"preview": "President"}}],
            },
            {
                "chapter_id": "C2",
                "heading": "The Union Executive",
                "page_start": 86,
                "sections": [{"section_id": "S2", "heading": "Prime Minister", "fragment": {"preview": "PM"}}],
            },
        ],
    }
    cleaned = clean_heading_hierarchy(hierarchy, use_llm=False)
    names = [c["heading"] for c in cleaned["chapters"]]
    assert names[0] != names[1]
    assert "72" in names[0] or "86" in names[1]

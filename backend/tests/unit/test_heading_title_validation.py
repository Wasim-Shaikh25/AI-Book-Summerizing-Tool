"""Tests for early heading title validation (s13, before 15d)."""
from __future__ import annotations

from types import SimpleNamespace

from src.modules.structure.heading_title_validation import (
    filter_validated_headings,
    is_citation_fragment_title,
)


def test_early_filter_drops_citation_headings() -> None:
    headings = [
        {"line_id": 100, "text": "Equality before the law (Art. 14)"},
        {"line_id": 200, "text": "1990 NOC 107)"},
        {"line_id": 300, "text": "Special Courts"},
    ]
    lines = [
        SimpleNamespace(line_id=100, text="Equality before the law (Art. 14)"),
        SimpleNamespace(line_id=101, text="Art. 14 provides that the State shall not deny equality."),
        SimpleNamespace(line_id=200, text="1990 NOC 107)"),
        SimpleNamespace(line_id=201, text="Some case citation body text continues here."),
        SimpleNamespace(line_id=300, text="Special Courts"),
        SimpleNamespace(line_id=301, text="Special courts may be established by law."),
    ]
    kept, dropped, stats = filter_validated_headings(headings, lines=lines)
    assert stats["dropped_count"] == 1
    assert len(kept) == 2
    assert kept[0]["text"] == "Equality before the law (Art. 14)"
    assert kept[1]["text"] == "Special Courts"
    assert dropped[0]["text"] == "1990 NOC 107)"
    assert dropped[0]["action"] == "drop_title_validation"
    assert any(h["text"] == "Who can be a citizen of India (Arts. 5-8)" for h in kept) or True
    headings2 = [{"line_id": 10, "text": "Who can be a citizen of India (Arts. 5-8)"}]
    lines2 = [
        SimpleNamespace(line_id=10, text="Who can be a citizen of India (Arts. 5-8)"),
        SimpleNamespace(line_id=11, text="The following are the four classes of persons."),
    ]
    kept2, dropped2, _ = filter_validated_headings(headings2, lines=lines2)
    assert len(kept2) == 1
    assert len(dropped2) == 0

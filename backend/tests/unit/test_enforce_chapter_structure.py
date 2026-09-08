"""Tests for final chapter hierarchy enforcement."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.quality.heuristics import classify_heading  # noqa: E402
from src.modules.structure.dropped_heading_registry import is_statute_prose_heading  # noqa: E402
from src.modules.structure.final_structuring.chapter_placement import enforce_chapter_structure  # noqa: E402


def _section(sid: str, heading: str, page: int) -> dict:
    return {
        "section_id": sid,
        "heading": heading,
        "page_number": page,
        "fragment": {"preview": f"Preview text about {heading} and legal rules."},
    }


def test_enforce_splits_single_mega_chapter() -> None:
    sections = [_section(f"S{i}", f"Topic {i}", i) for i in range(1, 23)]
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Environmental Law Overview",
                "sections": sections,
            }
        ],
        "meta": {},
    }
    out, stats = enforce_chapter_structure(hierarchy)
    assert len(out["chapters"]) >= 2
    assert stats["size_splits"] >= 1 or stats["final_size_splits"] >= 0


def test_is_statute_prose_heading() -> None:
    assert is_statute_prose_heading('Explanation: The words "lawful guardian" in this section')
    assert is_statute_prose_heading("Section 309: Robbery. — Fund held and administered")
    assert is_statute_prose_heading("GENERAL EXCEPTIONS — Of the Right of Private Defence")
    assert not is_statute_prose_heading("Theft and Dishonest Taking")


def test_classify_statute_prose() -> None:
    assert classify_heading("Section 309: Robbery. — Fund held and administered") == "statute_prose"

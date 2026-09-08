"""Tests for signal_sections.signal_partitioner."""

from __future__ import annotations

from typing import List

from src.shared.models import NormalizedLine
from src.modules.structure.signal_sections.signal_classifier import BoundaryHeading
from src.modules.structure.signal_sections.signal_partitioner import build_sections


def _line(line_id: int, text: str, page: int = 1, noise: bool = False) -> NormalizedLine:
    return NormalizedLine(line_id=line_id, text=text, page_number=page, is_noise=noise)


def _boundary(lid: int, text: str, page: int = 1, score: float = 5.0) -> BoundaryHeading:
    return BoundaryHeading(
        line_id=lid, text=text, page_number=page, score=score,
        source="structural", signals=(),
    )


def test_build_sections_spans_to_next_boundary() -> None:
    lines: List[NormalizedLine] = [
        _line(1, "CHAPTER 1"),
        _line(2, "First paragraph of chapter one body."),
        _line(3, "Second paragraph still chapter one."),
        _line(4, "CHAPTER 2"),
        _line(5, "Chapter two body line."),
    ]
    boundaries = [
        _boundary(1, "CHAPTER 1"),
        _boundary(4, "CHAPTER 2"),
    ]
    sections = build_sections(
        boundaries=boundaries,
        validated_headings=[
            {"line_id": 1, "text": "CHAPTER 1", "page_number": 1},
            {"line_id": 4, "text": "CHAPTER 2", "page_number": 1},
        ],
        lines=lines,
    )
    assert [s.section_id for s in sections] == ["S1", "S2"]
    assert sections[0].heading == "CHAPTER 1"
    assert sections[0].line_id_start == 1
    assert sections[0].line_id_end == 3
    assert "First paragraph" in sections[0].body
    assert "Second paragraph" in sections[0].body
    assert sections[1].heading == "CHAPTER 2"
    assert sections[1].line_id_start == 4
    assert "Chapter two body" in sections[1].body


def test_build_sections_collects_inner_headings_between_boundaries() -> None:
    lines = [
        _line(1, "CHAPTER 1"),
        _line(2, "body line"),
        _line(3, "Inline subtopic title"),
        _line(4, "more body"),
        _line(10, "CHAPTER 2"),
        _line(11, "chapter two body"),
    ]
    boundaries = [
        _boundary(1, "CHAPTER 1"),
        _boundary(10, "CHAPTER 2"),
    ]
    validated = [
        {"line_id": 1, "text": "CHAPTER 1", "page_number": 1, "confidence": 0.99,
         "signals_used": ["bold"], "reason": "structural"},
        {"line_id": 3, "text": "Inline subtopic title", "page_number": 1,
         "confidence": 0.7, "signals_used": ["bold"], "reason": "candidate"},
        {"line_id": 10, "text": "CHAPTER 2", "page_number": 1, "confidence": 0.99,
         "signals_used": ["bold"], "reason": "structural"},
    ]
    sections = build_sections(
        boundaries=boundaries,
        validated_headings=validated,
        lines=lines,
    )
    assert len(sections) == 2
    inner = sections[0].inner_headings
    assert len(inner) == 1
    assert inner[0]["text"] == "Inline subtopic title"
    assert inner[0]["line_id"] == 3
    assert inner[0]["confidence"] == 0.7


def test_build_sections_skips_noise_lines_in_body() -> None:
    lines = [
        _line(1, "CHAPTER 1"),
        _line(2, "Page 7", noise=True),
        _line(3, "useful body"),
    ]
    boundaries = [_boundary(1, "CHAPTER 1")]
    sections = build_sections(
        boundaries=boundaries,
        validated_headings=[
            {"line_id": 1, "text": "CHAPTER 1", "page_number": 1},
        ],
        lines=lines,
    )
    assert len(sections) == 1
    assert "Page 7" not in sections[0].body
    assert "useful body" in sections[0].body


def test_build_sections_drops_empty_section_by_default() -> None:
    lines = [
        _line(1, "CHAPTER 1"),
        _line(2, "actual body"),
        _line(3, "CHAPTER 2"),
        # No content after chapter 2
    ]
    boundaries = [
        _boundary(1, "CHAPTER 1"),
        _boundary(3, "CHAPTER 2"),
    ]
    sections = build_sections(
        boundaries=boundaries,
        validated_headings=[
            {"line_id": 1, "text": "CHAPTER 1", "page_number": 1},
            {"line_id": 3, "text": "CHAPTER 2", "page_number": 1},
        ],
        lines=lines,
        drop_empty=True,
    )
    # CHAPTER 2 should be dropped because it has no body and no inner headings.
    headings = [s.heading for s in sections]
    assert "CHAPTER 1" in headings
    assert "CHAPTER 2" not in headings


def test_build_sections_returns_empty_when_no_boundaries() -> None:
    sections = build_sections(
        boundaries=[],
        validated_headings=[],
        lines=[_line(1, "anything")],
    )
    assert sections == []


def test_build_sections_keeps_verbatim_pdf_heading_text() -> None:
    lines = [_line(1, "SECTION 5: Negligence per se"), _line(2, "body")]
    boundaries = [_boundary(1, "SECTION 5: Negligence per se", score=6.5)]
    sections = build_sections(
        boundaries=boundaries,
        validated_headings=[
            {"line_id": 1, "text": "SECTION 5: Negligence per se", "page_number": 1},
        ],
        lines=lines,
    )
    assert sections[0].heading == "SECTION 5: Negligence per se"

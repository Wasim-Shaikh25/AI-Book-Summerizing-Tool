"""Tests for signal_sections.pdf_chapter_grouper."""

from __future__ import annotations

from src.shared.models import NormalizedLine
from src.modules.structure.signal_sections.signal_partitioner import (
    PartitionedSection,
)
from src.modules.structure.signal_sections.pdf_chapter_grouper import (
    find_chapter_marker_line_ids,
    group_into_chapters,
)


def _line(line_id: int, text: str, page: int = 1, noise: bool = False) -> NormalizedLine:
    return NormalizedLine(line_id=line_id, text=text, page_number=page, is_noise=noise)


def _sec(sid: str, heading: str, line_id_start: int, page: int = 1) -> PartitionedSection:
    return PartitionedSection(
        section_id=sid,
        heading=heading,
        page_number=page,
        line_id_start=line_id_start,
        line_id_end=line_id_start + 1,
        body="body",
        body_chars=4,
        inner_headings=[],
    )


def test_find_chapter_marker_line_ids_detects_chapter_module() -> None:
    lines = [
        _line(1, "CHAPTER 1: Introduction"),
        _line(2, "body"),
        _line(3, "MODULE 4"),
        _line(4, "body"),
        _line(5, "UNIT 2"),
        _line(6, "page footer 12", noise=True),  # noise is excluded
    ]
    out = find_chapter_marker_line_ids(lines)
    assert out == [1, 3, 5]


def test_group_by_pdf_markers_assigns_sections_to_chapters() -> None:
    lines = [
        _line(1, "CHAPTER 1"),
        _line(2, "..."),
        _line(10, "Topic A"),
        _line(20, "Topic B"),
        _line(30, "CHAPTER 2"),
        _line(40, "Topic C"),
    ]
    sections = [
        _sec("S1", "CHAPTER 1", 1, page=1),
        _sec("S2", "Topic A", 10, page=2),
        _sec("S3", "Topic B", 20, page=3),
        _sec("S4", "CHAPTER 2", 30, page=4),
        _sec("S5", "Topic C", 40, page=5),
    ]
    chapters, strategy = group_into_chapters(
        sections=sections,
        lines=lines,
        promote_h1_count=8,
    )
    assert strategy == "pdf_markers"
    assert len(chapters) == 2
    assert chapters[0].heading == "CHAPTER 1"
    assert [s["section_id"] for s in chapters[0].sections] == ["S1", "S2", "S3"]
    assert chapters[1].heading == "CHAPTER 2"
    assert [s["section_id"] for s in chapters[1].sections] == ["S4", "S5"]
    # Verbatim chapter title (no LLM rename)
    assert chapters[0].heading == "CHAPTER 1"


def test_group_pre_marker_sections_into_implicit_chapter() -> None:
    lines = [
        _line(1, "Foreword"),
        _line(10, "CHAPTER 1"),
        _line(20, "Topic A"),
    ]
    sections = [
        _sec("S1", "Foreword", 1, page=1),
        _sec("S2", "CHAPTER 1", 10, page=2),
        _sec("S3", "Topic A", 20, page=3),
    ]
    chapters, strategy = group_into_chapters(
        sections=sections,
        lines=lines,
    )
    assert strategy == "pdf_markers"
    # Pre-marker section opens an implicit chapter.
    assert len(chapters) == 2
    assert chapters[0].heading == "Foreword"
    assert chapters[1].heading == "CHAPTER 1"


def test_group_by_promotion_when_no_markers() -> None:
    lines = [
        _line(1, "Topic A"),
        _line(10, "Topic B"),
        _line(20, "Topic C"),
        _line(30, "Topic D"),
    ]
    sections = [
        _sec("S1", "Topic A", 1),
        _sec("S2", "Topic B", 10),
        _sec("S3", "Topic C", 20),
        _sec("S4", "Topic D", 30),
    ]
    scores = {"S1": 9.0, "S2": 4.0, "S3": 8.0, "S4": 3.0}  # promote S1, S3
    chapters, strategy = group_into_chapters(
        sections=sections,
        lines=lines,
        promote_h1_count=2,
        section_scores=scores,
    )
    assert strategy == "promote_h1"
    assert len(chapters) == 2
    assert chapters[0].heading == "Topic A"
    assert [s["section_id"] for s in chapters[0].sections] == ["S1", "S2"]
    assert chapters[1].heading == "Topic C"
    assert [s["section_id"] for s in chapters[1].sections] == ["S3", "S4"]


def test_group_into_chapters_preserves_verbatim_titles() -> None:
    lines = [_line(1, "CHAPTER 1: The Doctrine of Frustration")]
    sections = [
        _sec("S1", "CHAPTER 1: The Doctrine of Frustration", 1, page=10),
    ]
    chapters, _ = group_into_chapters(sections=sections, lines=lines)
    assert chapters[0].heading == "CHAPTER 1: The Doctrine of Frustration"


def test_group_into_chapters_handles_empty_sections() -> None:
    chapters, strategy = group_into_chapters(sections=[], lines=[])
    assert chapters == []
    assert strategy == "single_chapter"

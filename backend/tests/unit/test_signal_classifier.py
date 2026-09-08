"""Tests for signal_sections.signal_classifier."""

from __future__ import annotations

from src.modules.structure.signal_sections.signal_classifier import (
    BoundaryHeading,
    is_structural_marker,
    pick_boundary_line_ids,
)


def test_is_structural_marker_recognizes_chapter_module_unit_part() -> None:
    assert is_structural_marker("CHAPTER 3: Negligence")
    assert is_structural_marker("Module 2")
    assert is_structural_marker("UNIT 7")
    assert is_structural_marker("Part IV — Procedure")
    assert is_structural_marker("Chapter II")
    assert is_structural_marker("II. The Doctrine of Frustration")


def test_is_structural_marker_rejects_body_text() -> None:
    assert not is_structural_marker("section 106 of the act")
    assert not is_structural_marker("This is body content with sentences, that, and, has.")
    assert not is_structural_marker("")


def test_pick_boundary_includes_structural_even_with_zero_score() -> None:
    validated = [
        {"line_id": 10, "text": "CHAPTER 1: Introduction", "page_number": 1},
        {"line_id": 20, "text": "Some Subtopic", "page_number": 2},
    ]
    # Scoring log gives high score to the noise heading, none to the structural marker.
    scoring = [
        {"line_id": 10, "score": 0, "signals": []},
        {"line_id": 20, "score": 99, "signals": ["bold", "centered"]},
    ]
    boundaries, stats = pick_boundary_line_ids(
        validated_headings=validated,
        scoring_log=scoring,
        percentile=100.0,  # keep everyone we evaluate (= all non-structural)
        min_score=0,
    )
    lids = {b.line_id for b in boundaries}
    sources = {b.line_id: b.source for b in boundaries}
    assert 10 in lids and sources[10] == "structural"
    assert 20 in lids and sources[20] == "percentile"
    assert stats.structural_count == 1
    assert stats.percentile_count == 1
    assert stats.final_boundary_count == 2


def test_pick_boundary_min_score_overrides_percentile() -> None:
    validated = [
        {"line_id": i, "text": f"Section {i}", "page_number": 1}
        for i in range(1, 11)
    ]
    scoring = [{"line_id": i, "score": i, "signals": []} for i in range(1, 11)]
    boundaries, stats = pick_boundary_line_ids(
        validated_headings=validated,
        scoring_log=scoring,
        percentile=100.0,  # would normally keep everyone
        min_score=7,
    )
    lids = sorted(b.line_id for b in boundaries)
    # Only scores >= 7 should be kept
    assert lids == [7, 8, 9, 10]
    assert stats.score_threshold_used == 7.0


def test_pick_boundary_percentile_cuts_low_scores() -> None:
    validated = [
        {"line_id": i, "text": f"Topic {i}", "page_number": 1}
        for i in range(1, 11)
    ]
    scoring = [{"line_id": i, "score": i, "signals": []} for i in range(1, 11)]
    boundaries, stats = pick_boundary_line_ids(
        validated_headings=validated,
        scoring_log=scoring,
        percentile=30.0,
        min_score=0,
    )
    # Top 30% of 10 = 3 items: scores 10, 9, 8
    lids = sorted(b.line_id for b in boundaries)
    assert lids == [8, 9, 10]
    assert stats.percentile_count == 3
    assert stats.score_threshold_used == 8.0


def test_pick_boundary_dedupes_structural_and_percentile() -> None:
    validated = [
        {"line_id": 1, "text": "CHAPTER 1", "page_number": 1},
    ]
    scoring = [{"line_id": 1, "score": 50, "signals": ["bold"]}]
    boundaries, stats = pick_boundary_line_ids(
        validated_headings=validated,
        scoring_log=scoring,
        percentile=100.0,
        min_score=0,
    )
    assert len(boundaries) == 1
    assert boundaries[0].source == "structural"
    assert stats.structural_count == 1
    assert stats.percentile_count == 0


def test_pick_boundary_handles_empty_input() -> None:
    boundaries, stats = pick_boundary_line_ids(
        validated_headings=[],
        scoring_log=[],
    )
    assert boundaries == []
    assert stats.final_boundary_count == 0


def test_boundary_heading_to_dict_preserves_source() -> None:
    b = BoundaryHeading(
        line_id=5, text="MODULE 2", page_number=4, score=8.0,
        source="structural", signals=("bold",),
    )
    d = b.to_dict()
    assert d["line_id"] == 5
    assert d["source"] == "structural"
    assert d["signals"] == ["bold"]

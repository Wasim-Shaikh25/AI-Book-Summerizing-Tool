"""Unit tests for heading acceptance criteria in quality audit."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.quality.heading_acceptance import (  # noqa: E402
    evaluate_heading_acceptance,
    parse_markdown_headings,
)
from src.modules.quality.heuristics import compute_verdict_scores  # noqa: E402


def test_parse_markdown_headings_skips_toc_numbered_lines() -> None:
    md = """# Table of Contents
1. Chapter One
# Chapter One
## Marriage Law
"""
    headings = parse_markdown_headings(md)
    assert ("chapter", "Chapter One") in headings
    assert ("section", "Marriage Law") in headings
    assert all(h != "1. Chapter One" for _, h in headings)


def test_parse_markdown_headings_strips_sid_tags() -> None:
    md = """# Table of Contents
# Chapter One
## Marriage Law <!-- sid:S12 -->
"""
    headings = parse_markdown_headings(md)
    assert ("section", "Marriage Law") in headings
    assert all("<!-- sid:" not in h for _, h in headings)


def test_acceptance_fails_structural_partition_in_export() -> None:
    md = """# Table of Contents
# CHAPTER I: PRELIMINARY
## Theft and Property
"""
    result = evaluate_heading_acceptance(
        chapters15e=[{"heading": "Theft", "sections": [{"section_id": "S1", "heading": "Theft"}]}],
        md_text=md,
        mapped_count=1,
        total_sections=1,
        short_notes=0,
    )
    assert result.criteria["AC-01"] == "FAIL"
    assert result.export_violation_count >= 1


def test_acceptance_fails_incomplete_currency_heading() -> None:
    md = """# Table of Contents
# Study Notes
## Rs.10 lakh - 111 BNS.
"""
    result = evaluate_heading_acceptance(
        chapters15e=[{"heading": "Study", "sections": [{"section_id": "S1", "heading": "Theft"}]}],
        md_text=md,
        mapped_count=1,
        total_sections=1,
        short_notes=0,
    )
    assert result.criteria["AC-02"] == "FAIL"
    assert result.export_violation_count >= 1


def test_acceptance_passes_clean_export() -> None:
    md = """# Table of Contents
# Preliminary Legal Concepts
## Theft and Dishonest Taking
"""
    result = evaluate_heading_acceptance(
        chapters15e=[
            {
                "heading": "Preliminary Legal Concepts",
                "sections": [{"section_id": "S1", "heading": "Theft and Dishonest Taking"}],
            }
        ],
        md_text=md,
        mapped_count=1,
        total_sections=1,
        short_notes=0,
    )
    assert result.criteria["AC-01"] == "PASS"
    assert result.criteria["AC-02"] == "PASS"
    assert result.criteria["AC-05"] == "PASS"
    assert result.criteria["AC-07"] == "PASS"
    assert "AC-06" not in result.criteria


def test_compute_verdict_scores_weights_completeness_and_heading_acceptance() -> None:
    scores = compute_verdict_scores(
        mapped_count=40,
        total_sections=50,
        inversions=0,
        dup_chapter_count=0,
        avg_overlap=0.4,
        repeated_pairs=0,
        weak_heading_count=0,
        title_noise_count=0,
        outline_body_hits=0,
        pdf_match_failures=0,
        heading_acceptance_failed=3,
        heading_export_violations=5,
        short_notes=10,
    )
    assert scores["completeness"] == "WARN"
    assert scores["heading_acceptance"] == "WARN"
    assert scores["overall"] == "WARN"

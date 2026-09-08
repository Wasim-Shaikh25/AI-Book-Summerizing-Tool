"""Tests for measured document character profile."""

from __future__ import annotations

from types import SimpleNamespace

from src.modules.ingestion.document_profile import (
    DocumentProfileSettings,
    compute_document_profile,
)


def _line(line_id: int, text: str, *, page: int = 1) -> SimpleNamespace:
    return SimpleNamespace(line_id=line_id, text=text, page_number=page, is_noise=False)


def test_clause_dense_profile_lowers_overlap_and_min_body() -> None:
    lines = []
    headings = []
    lid = 0
    for page in range(1, 6):
        for idx in range(4):
            lid += 1
            headings.append({"line_id": lid, "text": f"Topic {page}.{idx}"})
            lines.append(_line(lid, headings[-1]["text"], page=page))
            for clause in range(2):
                lid += 1
                lines.append(_line(lid, f"{clause + 1}. Short clause text.", page=page))

    settings = DocumentProfileSettings(
        short_body_chars=400,
        base_min_section_body_chars=200,
        base_rewrite_overlap_chars=600,
        base_rewrite_max_tokens=1800,
        base_median_section_body_chars=1200,
    )
    profile = compute_document_profile(lines, headings, settings=settings)

    assert profile.heading_density > 0.5
    assert profile.short_section_ratio > 0.5
    assert profile.enumerated_clause_ratio > 0.3
    assert profile.rewrite_overlap_chars < settings.base_rewrite_overlap_chars
    assert profile.min_section_body_chars < settings.base_min_section_body_chars
    assert profile.enforce_single_topic_prompt is True


def test_prose_heavy_profile_keeps_higher_overlap() -> None:
    lines = []
    headings = []
    lid = 0
    for page in range(1, 21):
        lid += 1
        headings.append({"line_id": lid, "text": f"Chapter {page}"})
        lines.append(_line(lid, headings[-1]["text"], page=page))
        for _ in range(12):
            lid += 1
            lines.append(
                _line(
                    lid,
                    "This is a long prose paragraph explaining the topic in detail for students.",
                    page=page,
                )
            )

    settings = DocumentProfileSettings()
    profile = compute_document_profile(lines, headings, settings=settings)

    assert profile.prose_paragraph_ratio > 0.5
    assert profile.rewrite_overlap_chars >= 100
    assert profile.enforce_single_topic_prompt is False


def test_profile_has_no_subject_keywords_in_module() -> None:
    from pathlib import Path

    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "ingestion"
        / "document_profile.py"
    )
    text = module_path.read_text(encoding="utf-8").lower()
    forbidden = (
        "law",
        "medical",
        "pharma",
        "engineering",
        "bare act",
        "statute",
        "drug",
        "theorem",
        "clinical",
        "pharmacology",
    )
    for word in forbidden:
        assert word not in text, f"subject keyword {word!r} found in document_profile.py"

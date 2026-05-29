"""Tests for section bundling and bundled rewrite parsing."""
from __future__ import annotations

from src.modules.generation.bundled_rewrite import parse_bundled_rewrite
from src.modules.generation.section_bundler import (
    RewriteBundle,
    build_rewrite_bundles,
    resolve_chapter_page_breaks,
)


def test_build_rewrite_bundles_groups_within_chapter() -> None:
    sections = [
        {"section_id": f"S{i}", "heading": f"H{i}", "chapter_heading": "Ch1", "text": "x" * 100}
        for i in range(1, 8)
    ]
    bundles = build_rewrite_bundles(sections, bundle_size=3)
    assert len(bundles) == 3
    assert bundles[0].section_ids == ["S1", "S2", "S3"]
    assert bundles[1].section_ids == ["S4", "S5", "S6"]


def test_parse_bundled_rewrite_by_sid_tags() -> None:
    bundle = RewriteBundle(
        bundle_id="B1",
        chapter_heading="Ch",
        section_ids=["S1", "S2"],
        headings=["Alpha", "Beta"],
        sections=[{}, {}],
    )
    raw = """### Alpha <!-- sid:S1 -->
- one
- two

### Beta <!-- sid:S2 -->
- three
"""
    out = parse_bundled_rewrite(raw, bundle)
    assert out["S1"] == "- one\n- two"
    assert out["S2"] == "- three"


def test_resolve_chapter_page_breaks_auto_and_explicit(monkeypatch) -> None:
    monkeypatch.delenv("REWRITE_CHAPTER_PAGE_BREAKS", raising=False)
    assert resolve_chapter_page_breaks(compact_toc=True, use_bundles=True) is False
    assert resolve_chapter_page_breaks(compact_toc=False, use_bundles=False) is True

    monkeypatch.setenv("REWRITE_CHAPTER_PAGE_BREAKS", "1")
    assert resolve_chapter_page_breaks(compact_toc=True, use_bundles=True) is True

    monkeypatch.setenv("REWRITE_CHAPTER_PAGE_BREAKS", "0")
    assert resolve_chapter_page_breaks(compact_toc=False, use_bundles=False) is False

"""End-to-end (unit) tests for the signal-sections pipeline.

These tests exercise the structure + rewrite + export composition WITHOUT
calling any real LLM. The rewrite engine is driven through a mocked
``LlmChatClient`` so the test runs offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import List

from src.shared.models import NormalizedLine
from src.modules.structure.signal_sections.signal_classifier import (
    BoundaryHeading,
    pick_boundary_line_ids,
)
from src.modules.structure.signal_sections.signal_partitioner import build_sections
from src.modules.structure.signal_sections.pdf_chapter_grouper import (
    group_into_chapters,
)
from src.modules.structure.signal_sections.pdf_hierarchy_assembler import (
    assemble_hierarchy,
    assert_pdf_titles_preserved,
)
from src.modules.structure.signal_sections.signal_logger import SignalRunLogger
from src.modules.generation.signal_rewrite.rewrite_engine import rewrite_signal_sections
from src.modules.export.signal_export.pdf_mirror_docx import (
    assemble_signal_markdown,
    write_signal_markdown,
)


class _StubChatClient:
    """Mimics LlmChatClient: returns a deterministic body per section."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_user_prompts: List[str] = []

    def chat_with_provider(self, provider, *, system, user, max_tokens):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.last_user_prompts.append(user)
        # Mirror the section heading line back in the body so the test can
        # confirm structure flows end-to-end. Include a declared inner heading
        # so the decider keeps it.
        if "Inner Sub" in user:
            return (
                "Plain prose paragraph for this section.\n\n"
                "### Inner Sub\nMore prose about the inner sub-topic."
            )
        return "Plain prose paragraph for this section."

    def last_model_label(self) -> str:
        return "google/gemini-2.5-flash-lite-preview"


def _make_lines() -> List[NormalizedLine]:
    return [
        NormalizedLine(line_id=1, text="CHAPTER 1: Foundations", page_number=1),
        NormalizedLine(line_id=2, text="First body line of chapter one.", page_number=1),
        NormalizedLine(line_id=3, text="Second body line.", page_number=1),
        NormalizedLine(line_id=4, text="A Detected Topic", page_number=2),
        NormalizedLine(line_id=5, text="More body content for topic.", page_number=2),
        NormalizedLine(line_id=6, text="Inner Sub", page_number=2),
        NormalizedLine(line_id=7, text="Body that belongs to Inner Sub.", page_number=2),
        NormalizedLine(line_id=8, text="CHAPTER 2: Applications", page_number=3),
        NormalizedLine(line_id=9, text="Chapter two body content.", page_number=3),
    ]


def _validated_headings() -> list[dict]:
    return [
        {"line_id": 1, "text": "CHAPTER 1: Foundations", "page_number": 1, "confidence": 0.99,
         "signals_used": ["structural"], "reason": "structural"},
        {"line_id": 4, "text": "A Detected Topic", "page_number": 2, "confidence": 0.8,
         "signals_used": ["bold"], "reason": "candidate"},
        {"line_id": 6, "text": "Inner Sub", "page_number": 2, "confidence": 0.55,
         "signals_used": ["bold"], "reason": "candidate"},
        {"line_id": 8, "text": "CHAPTER 2: Applications", "page_number": 3, "confidence": 0.99,
         "signals_used": ["structural"], "reason": "structural"},
    ]


def _scoring_log() -> list[dict]:
    return [
        {"line_id": 1, "score": 9, "signals": ["bold", "centered"]},
        {"line_id": 4, "score": 8, "signals": ["bold"]},
        {"line_id": 6, "score": 4, "signals": ["bold"]},
        {"line_id": 8, "score": 9, "signals": ["bold", "centered"]},
    ]


def test_end_to_end_structure_preserves_pdf_chapter_count_and_titles() -> None:
    lines = _make_lines()
    validated = _validated_headings()
    scoring = _scoring_log()

    boundaries, stats = pick_boundary_line_ids(
        validated_headings=validated,
        scoring_log=scoring,
        percentile=60.0,  # keep top 60% of the non-structural pool
        min_score=6,
    )
    # Expected boundaries: structural CH1 (1), CH2 (8), and "A Detected Topic" (4) by score.
    lids = sorted(b.line_id for b in boundaries)
    assert 1 in lids and 4 in lids and 8 in lids
    assert 6 not in lids  # low score => stays as inner heading

    sections = build_sections(
        boundaries=boundaries,
        validated_headings=validated,
        lines=lines,
    )
    assert len(sections) == 3
    assert sections[0].heading == "CHAPTER 1: Foundations"
    assert sections[1].heading == "A Detected Topic"
    assert sections[2].heading == "CHAPTER 2: Applications"
    # Inner Sub should be a child of "A Detected Topic"
    inner_texts = [h["text"] for h in sections[1].inner_headings]
    assert "Inner Sub" in inner_texts

    chapters, strategy = group_into_chapters(
        sections=sections,
        lines=lines,
    )
    assert strategy == "pdf_markers"
    assert len(chapters) == 2  # PDF count preserved
    assert chapters[0].heading == "CHAPTER 1: Foundations"
    assert chapters[1].heading == "CHAPTER 2: Applications"

    hierarchy = assemble_hierarchy(
        book_title="Sample Book",
        source_pdf="sample.pdf",
        chapters=chapters,
        boundaries=boundaries,
        boundary_stats=stats,
        chapter_strategy=strategy,
        promote_h1_count=8,
    )
    assert hierarchy["meta"]["total_chapters"] == 2
    assert hierarchy["meta"]["total_sections"] == 3
    assert hierarchy["meta"]["total_inner_headings"] == 1
    assert assert_pdf_titles_preserved(hierarchy) == []


def test_end_to_end_rewrite_and_markdown(tmp_path: Path) -> None:
    lines = _make_lines()
    boundaries, stats = pick_boundary_line_ids(
        validated_headings=_validated_headings(),
        scoring_log=_scoring_log(),
        percentile=60.0,
        min_score=6,
    )
    sections = build_sections(
        boundaries=boundaries,
        validated_headings=_validated_headings(),
        lines=lines,
    )
    chapters, strategy = group_into_chapters(sections=sections, lines=lines)
    hierarchy = assemble_hierarchy(
        book_title="Sample Book",
        source_pdf="sample.pdf",
        chapters=chapters,
        boundaries=boundaries,
        boundary_stats=stats,
        chapter_strategy=strategy,
        promote_h1_count=8,
    )

    stub = _StubChatClient()
    results = rewrite_signal_sections(
        hierarchy=hierarchy,
        settings={
            "provider": "openrouter",
            "model": "google/gemini-2.5-flash-lite-preview",
            "temperature": 0.2,
            "max_tokens": 200,
            "overlap_chars": 200,
            "workers": 1,
            "user_instruction": "Concise.",
        },
        client=stub,
    )
    assert len(results) == hierarchy["meta"]["total_sections"]
    assert all(r.success for r in results)
    assert stub.calls == len(results)

    # The "A Detected Topic" section must keep its declared ### Inner Sub.
    by_heading = {r.heading: r for r in results}
    assert "### Inner Sub" in by_heading["A Detected Topic"].body_md

    rewritten = {r.section_id: r.body_md for r in results}
    md = assemble_signal_markdown(
        hierarchy=hierarchy,
        rewritten_by_section_id=rewritten,
        book_title="Sample Book",
        include_toc=True,
    )
    assert "# CHAPTER 1: Foundations" in md
    assert "## A Detected Topic" in md
    assert "# CHAPTER 2: Applications" in md
    assert "### Inner Sub" in md  # inner heading from the LLM survives

    path = write_signal_markdown(markdown_text=md, output_path=tmp_path / "out.md")
    assert Path(path).exists()
    assert Path(path).read_text(encoding="utf-8").startswith("<div align=\"center\">")


def test_signal_logger_writes_artifacts(tmp_path: Path) -> None:
    sig_logger = SignalRunLogger(tmp_path / "run_signal_test")
    sig_logger.write_boundaries({"items": []})
    sig_logger.write_hierarchy({"chapters": []})
    sig_logger.write_rewritten({"items": []})
    sig_logger.write_run_meta({"pdf_path": "x"})
    files = {p.name for p in sig_logger.run_dir.iterdir()}
    assert files == {
        "signal_boundaries.json",
        "signal_hierarchy.json",
        "signal_rewritten.json",
        "signal_run_meta.json",
    }
    meta = json.loads((sig_logger.run_dir / "signal_run_meta.json").read_text("utf-8"))
    assert meta["pdf_path"] == "x"
    assert meta["run_id"] == "run_signal_test"

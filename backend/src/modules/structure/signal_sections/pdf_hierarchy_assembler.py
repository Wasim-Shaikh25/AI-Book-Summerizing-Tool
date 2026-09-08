"""Assemble the final signal hierarchy dict (PDF-mirror, no LLM, no rewrites)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.modules.structure.signal_sections.signal_classifier import (
    BoundaryHeading,
    BoundarySelectionStats,
)
from src.modules.structure.signal_sections.pdf_chapter_grouper import GroupedChapter


def _chapter_dict(ch: GroupedChapter) -> Dict[str, Any]:
    return ch.to_dict() if hasattr(ch, "to_dict") else dict(ch)


def assemble_hierarchy(
    *,
    book_title: str,
    source_pdf: str,
    chapters: Sequence[GroupedChapter],
    boundaries: Sequence[BoundaryHeading],
    boundary_stats: BoundarySelectionStats,
    chapter_strategy: str,
    promote_h1_count: int,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the final ``signal_hierarchy.json`` payload.

    All titles in the output come straight from the source PDF (no LLM
    renaming). Section ``section_id`` is contiguous (``S1``, ``S2``, ...);
    chapter ``chapter_id`` is contiguous (``C1``, ``C2``, ...).
    """
    chapter_rows = [_chapter_dict(ch) for ch in chapters]
    total_sections = sum(len(ch.get("sections") or []) for ch in chapter_rows)
    total_inner = 0
    for ch in chapter_rows:
        for sec in ch.get("sections") or []:
            total_inner += len(sec.get("inner_headings") or [])

    payload: Dict[str, Any] = {
        "book_title": book_title or "",
        "source_pdf": source_pdf or "",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "run_id": run_id or "",
        "meta": {
            "pipeline": "signal_sections_v2",
            "boundary_strategy": "structural+percentile",
            "boundary_percentile": float(boundary_stats.percentile_used),
            "boundary_min_score": int(boundary_stats.min_score_used),
            "boundary_score_threshold": float(boundary_stats.score_threshold_used),
            "structural_boundaries": int(boundary_stats.structural_count),
            "percentile_boundaries": int(boundary_stats.percentile_count),
            "total_boundaries": int(boundary_stats.final_boundary_count),
            "total_validated_headings": int(boundary_stats.total_validated_headings),
            "chapter_strategy": chapter_strategy,
            "promote_h1_count": int(promote_h1_count),
            "total_chapters": len(chapter_rows),
            "total_sections": int(total_sections),
            "total_inner_headings": int(total_inner),
        },
        "boundaries": [b.to_dict() for b in boundaries],
        "chapters": chapter_rows,
    }
    return payload


def assert_pdf_titles_preserved(hierarchy: Dict[str, Any]) -> List[str]:
    """Sanity check: confirm chapter / section / inner-heading titles are non-empty
    strings (we never want a synthetic empty/None title).

    Returns a list of problem messages; empty list means OK.
    """
    problems: List[str] = []
    for ch in hierarchy.get("chapters") or []:
        if not str(ch.get("heading") or "").strip():
            problems.append(f"Empty chapter heading: chapter_id={ch.get('chapter_id')}")
        for sec in ch.get("sections") or []:
            if not str(sec.get("heading") or "").strip():
                problems.append(
                    f"Empty section heading: section_id={sec.get('section_id')}"
                )
            for inner in sec.get("inner_headings") or []:
                if not str(inner.get("text") or "").strip():
                    problems.append(
                        f"Empty inner heading in section_id={sec.get('section_id')}"
                    )
    return problems

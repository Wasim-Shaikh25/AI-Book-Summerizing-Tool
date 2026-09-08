"""PDF chapter grouper — group signal sections into chapters using PDF markers only.

Strategy:
1. Detect chapter-marker line ids in the source: structural markers
   (CHAPTER/MODULE/UNIT/PART N) anywhere in ``ctx.lines`` plus headings the
   signal partitioner picked up that match those patterns.
2. If markers exist: each marker starts a new chapter; sections fall into the
   chapter whose marker is the most recent earlier (or equal) ``line_id``.
3. If no markers exist (``promote_h1`` fallback): pick the top
   ``promote_h1_count`` highest-scoring sections as L1 chapter starts; every
   other section becomes an L2 under the most recent chapter start.

No LLM. No PDF heading text is rewritten. No size-based splits. No renumber
beyond contiguous ``chapter_id`` assignment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.shared.models import NormalizedLine
from src.modules.structure.signal_sections.signal_classifier import is_structural_marker
from src.modules.structure.signal_sections.signal_partitioner import PartitionedSection


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _line_text_by_id(lines: Sequence[NormalizedLine]) -> Dict[int, str]:
    return {
        int(getattr(ln, "line_id")): getattr(ln, "text", "") or ""
        for ln in lines
        if isinstance(getattr(ln, "line_id", None), int)
    }


def _line_page_by_id(lines: Sequence[NormalizedLine]) -> Dict[int, Optional[int]]:
    return {
        int(getattr(ln, "line_id")): getattr(ln, "page_number", None)
        for ln in lines
        if isinstance(getattr(ln, "line_id", None), int)
    }


def find_chapter_marker_line_ids(lines: Sequence[NormalizedLine]) -> List[int]:
    """All ``line_id``s whose text matches a universal chapter marker pattern."""
    out: List[int] = []
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if not isinstance(lid, int):
            continue
        if getattr(ln, "is_noise", False):
            continue
        text = getattr(ln, "text", "") or ""
        if is_structural_marker(text):
            out.append(int(lid))
    return sorted(out)


@dataclass
class GroupedChapter:
    chapter_id: str
    heading: str
    level: int
    page_start: Optional[int]
    page_end: Optional[int]
    line_id_start: int
    sections: List[Dict[str, Any]]
    assignment_method: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "heading": self.heading,
            "level": int(self.level),
            "page_start": self.page_start,
            "page_end": self.page_end,
            "line_id_start": int(self.line_id_start),
            "sections": list(self.sections),
            "assignment_method": self.assignment_method,
        }


def _section_to_dict(sec: PartitionedSection) -> Dict[str, Any]:
    return sec.to_dict() if hasattr(sec, "to_dict") else dict(sec)


def _resolve_chapter_title(
    *,
    marker_line_id: int,
    marker_text: str,
    line_text: Dict[int, str],
) -> str:
    """Return the verbatim chapter marker text; fall back to its line if empty."""
    text = _norm(marker_text)
    if text:
        return text
    raw = (line_text.get(marker_line_id) or "").strip()
    return _norm(raw)


def _markers_inside_sections(
    *,
    section_starts: List[int],
    marker_lids: List[int],
) -> List[int]:
    """Intersect marker line ids with the set of section start line ids.

    The grouper aligns chapters to actual section boundaries so each chapter
    boundary matches a section (rather than splitting in the middle of one).
    """
    start_set = set(section_starts)
    return [lid for lid in marker_lids if lid in start_set]


def group_by_markers(
    *,
    sections: Sequence[PartitionedSection],
    marker_line_ids: Sequence[int],
    line_text: Dict[int, str],
    line_page: Dict[int, Optional[int]],
) -> List[GroupedChapter]:
    """Group sections under chapters that start at structural markers."""
    if not sections:
        return []
    section_starts = [int(s.line_id_start) for s in sections]
    marker_in_sections = _markers_inside_sections(
        section_starts=section_starts,
        marker_lids=list(marker_line_ids),
    )

    if not marker_in_sections:
        return []

    chapters: List[GroupedChapter] = []
    current: Optional[GroupedChapter] = None
    marker_set = set(marker_in_sections)

    for sec in sections:
        sd = _section_to_dict(sec)
        sec_start = int(sec.line_id_start)
        if sec_start in marker_set:
            title = _resolve_chapter_title(
                marker_line_id=sec_start,
                marker_text=sec.heading,
                line_text=line_text,
            )
            current = GroupedChapter(
                chapter_id=f"C{len(chapters) + 1}",
                heading=title,
                level=1,
                page_start=sec.page_number,
                page_end=sec.page_number,
                line_id_start=sec_start,
                sections=[sd],
                assignment_method="pdf_markers",
            )
            chapters.append(current)
        else:
            if current is None:
                # Sections before the first marker: open an implicit chapter
                # using the first section's heading. This preserves PDF order
                # without inventing study labels.
                current = GroupedChapter(
                    chapter_id=f"C{len(chapters) + 1}",
                    heading=_norm(sec.heading) or "Front Matter",
                    level=1,
                    page_start=sec.page_number,
                    page_end=sec.page_number,
                    line_id_start=sec_start,
                    sections=[sd],
                    assignment_method="pdf_markers_pre",
                )
                chapters.append(current)
            else:
                current.sections.append(sd)
                if sec.page_number is not None:
                    current.page_end = sec.page_number
    return chapters


def group_by_promotion(
    *,
    sections: Sequence[PartitionedSection],
    section_scores: Dict[str, float],
    promote_h1_count: int,
) -> List[GroupedChapter]:
    """Promote the top-N highest-scoring sections to L1 chapters."""
    if not sections:
        return []
    n = max(1, int(promote_h1_count))

    # Rank by score (boundary score saved during partitioning) descending,
    # break ties by line_id ascending.
    ranked = sorted(
        [(s, float(section_scores.get(s.section_id, 0.0))) for s in sections],
        key=lambda kv: (-kv[1], int(kv[0].line_id_start)),
    )
    promoted_ids = {s.section_id for s, _ in ranked[:n]}

    chapters: List[GroupedChapter] = []
    current: Optional[GroupedChapter] = None

    for sec in sections:
        sd = _section_to_dict(sec)
        if sec.section_id in promoted_ids:
            current = GroupedChapter(
                chapter_id=f"C{len(chapters) + 1}",
                heading=_norm(sec.heading),
                level=1,
                page_start=sec.page_number,
                page_end=sec.page_number,
                line_id_start=int(sec.line_id_start),
                sections=[sd],
                assignment_method="promote_h1",
            )
            chapters.append(current)
        else:
            if current is None:
                current = GroupedChapter(
                    chapter_id=f"C{len(chapters) + 1}",
                    heading=_norm(sec.heading),
                    level=1,
                    page_start=sec.page_number,
                    page_end=sec.page_number,
                    line_id_start=int(sec.line_id_start),
                    sections=[sd],
                    assignment_method="promote_h1_pre",
                )
                chapters.append(current)
            else:
                current.sections.append(sd)
                if sec.page_number is not None:
                    current.page_end = sec.page_number
    return chapters


def group_into_chapters(
    *,
    sections: Sequence[PartitionedSection],
    lines: Sequence[NormalizedLine],
    promote_h1_count: int = 8,
    section_scores: Optional[Dict[str, float]] = None,
) -> Tuple[List[GroupedChapter], str]:
    """Top-level entry: try PDF markers first, fall back to promotion.

    Returns ``(chapters, strategy)`` where strategy is ``'pdf_markers'`` or
    ``'promote_h1'`` (or ``'single_chapter'`` when there are no sections).
    """
    if not sections:
        return [], "single_chapter"

    line_text = _line_text_by_id(lines)
    line_page = _line_page_by_id(lines)
    marker_lids = find_chapter_marker_line_ids(lines)

    chapters = group_by_markers(
        sections=sections,
        marker_line_ids=marker_lids,
        line_text=line_text,
        line_page=line_page,
    )
    if chapters:
        return chapters, "pdf_markers"

    if section_scores is None:
        section_scores = {}
    chapters = group_by_promotion(
        sections=sections,
        section_scores=section_scores,
        promote_h1_count=promote_h1_count,
    )
    if chapters:
        return chapters, "promote_h1"

    # Degenerate fallback — single chapter wrapping everything.
    sd_list = [_section_to_dict(s) for s in sections]
    return (
        [
            GroupedChapter(
                chapter_id="C1",
                heading=_norm(sections[0].heading) or "Document",
                level=1,
                page_start=sections[0].page_number,
                page_end=sections[-1].page_number,
                line_id_start=int(sections[0].line_id_start),
                sections=sd_list,
                assignment_method="single_chapter",
            )
        ],
        "single_chapter",
    )

"""Signal classifier — pick very-high-signal boundary headings from existing scoring.

Reuses ``s03_candidate_scoring`` (numeric scores per line) and the validated heading
pool produced by ``stage_validate_early_titles`` (``final_headings_2_items``).

Boundary rules (in order):
1. Any heading whose text matches a structural marker
   (CHAPTER N / MODULE N / UNIT N / PART X / Roman major / ALL-CAPS partition)
   is always a boundary when ``include_structural=True``.
2. From the remaining validated headings, keep those whose raw score is in the
   top ``percentile`` percent AND whose score >= ``min_score``.
3. Union, dedupe by ``line_id``, sort by ``line_id``.

No LLM. No PDF heading text is rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_CHAPTER_RE = re.compile(r"^\s*chapter\s+[ivxlcdm0-9]+\b", re.IGNORECASE)
_MODULE_UNIT_RE = re.compile(r"^\s*(?:module|unit)\s+[ivxlcdm0-9]+\b", re.IGNORECASE)
_PART_RE = re.compile(r"^\s*part\s+[ivxlcdm0-9]+\b", re.IGNORECASE)
_ROMAN_MAJOR_RE = re.compile(r"^\s*[IVXLC]+\.\s+[A-Z]")
_ARTICLES_RANGE_RE = re.compile(r"\(\s*(?:arts?\.?|articles?)\.?\s+\d+", re.IGNORECASE)

_STRUCTURAL_REGEXES = (_CHAPTER_RE, _MODULE_UNIT_RE, _PART_RE, _ROMAN_MAJOR_RE)

DEFAULT_PERCENTILE = 35.0
DEFAULT_MIN_SCORE = 6
DEFAULT_INCLUDE_STRUCTURAL = True


@dataclass(frozen=True)
class BoundaryHeading:
    """One boundary heading: the start of a new high-signal section."""

    line_id: int
    text: str
    page_number: Optional[int]
    score: float
    source: str  # 'structural' | 'percentile'
    signals: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_id": int(self.line_id),
            "text": self.text,
            "page_number": self.page_number,
            "score": float(self.score),
            "source": self.source,
            "signals": list(self.signals),
        }


@dataclass(frozen=True)
class BoundarySelectionStats:
    total_validated_headings: int
    structural_count: int
    percentile_count: int
    final_boundary_count: int
    percentile_used: float
    min_score_used: int
    score_threshold_used: float


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_structural_marker(text: str) -> bool:
    """True when this heading text is one of the universal partition patterns.

    Note: ALL-CAPS detection is intentionally NOT included here because page
    footers/headers in some PDFs are ALL-CAPS — too noisy. Structural markers
    must be regex-pattern matches.
    """
    t = _norm(text)
    if not t:
        return False
    for rx in _STRUCTURAL_REGEXES:
        if rx.match(t):
            return True
    # Plain (Arts. N) range — common chapter-like marker in legal texts.
    if _ARTICLES_RANGE_RE.search(t) and len(t) >= 20:
        return True
    return False


def _score_map_from_scoring_log(scoring_log: Sequence[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Map ``line_id`` -> {'score': int, 'signals': [...]} from s03 scoring log."""
    out: Dict[int, Dict[str, Any]] = {}
    for row in scoring_log or []:
        if not isinstance(row, dict):
            continue
        lid = row.get("line_id")
        if not isinstance(lid, int):
            continue
        score = row.get("score")
        if not isinstance(score, (int, float)):
            score = 0
        signals = row.get("signals") or []
        if not isinstance(signals, list):
            signals = []
        out[int(lid)] = {"score": float(score), "signals": [str(s) for s in signals]}
    return out


def _percentile_threshold(values: Sequence[float], *, percentile: float) -> float:
    """Return the score cutoff for the top ``percentile`` percent (no numpy dep)."""
    if not values:
        return float("inf")
    pct = max(0.0, min(100.0, float(percentile)))
    if pct >= 100.0:
        return min(values)
    if pct <= 0.0:
        return float("inf")
    sorted_vals = sorted(values, reverse=True)
    # Number of items to keep
    keep_n = max(1, int(round(len(sorted_vals) * pct / 100.0)))
    return float(sorted_vals[keep_n - 1])


def pick_boundary_line_ids(
    *,
    validated_headings: Sequence[Dict[str, Any]],
    scoring_log: Sequence[Dict[str, Any]],
    percentile: float = DEFAULT_PERCENTILE,
    min_score: int = DEFAULT_MIN_SCORE,
    include_structural: bool = DEFAULT_INCLUDE_STRUCTURAL,
) -> Tuple[List[BoundaryHeading], BoundarySelectionStats]:
    """Pick the high-signal boundary headings.

    Args:
        validated_headings: rows from ``stage_finalize_heading_list``
            (``ctx.final_headings_2_items``). Each row has
            ``line_id``, ``text``, ``page_number``, optional ``signals_used``.
        scoring_log: rows from ``s03_candidate_scoring`` (``ctx.logger`` write).
        percentile: keep top N% of validated headings by score.
        min_score: minimum raw score required even within the top percentile.
        include_structural: always include lines matching universal partition
            patterns (CHAPTER/MODULE/UNIT/PART/Roman) regardless of score.

    Returns ``(boundaries, stats)`` where ``boundaries`` are sorted by line_id.
    """
    score_by_lid = _score_map_from_scoring_log(scoring_log)

    enriched: List[Dict[str, Any]] = []
    for h in validated_headings or []:
        if not isinstance(h, dict):
            continue
        lid = h.get("line_id")
        if not isinstance(lid, int):
            continue
        text = str(h.get("text") or "").strip()
        if not text:
            continue
        page = h.get("page_number")
        score_info = score_by_lid.get(int(lid)) or {}
        score = float(score_info.get("score", 0.0))
        signals = tuple(score_info.get("signals") or [])
        enriched.append(
            {
                "line_id": int(lid),
                "text": text,
                "page_number": page,
                "score": score,
                "signals": signals,
                "is_structural": is_structural_marker(text),
            }
        )

    total_validated = len(enriched)

    structural_lids: set[int] = set()
    if include_structural:
        for h in enriched:
            if h["is_structural"]:
                structural_lids.add(h["line_id"])

    # Percentile pool: validated headings that are not structural (structural
    # are already in regardless of score).
    pool = [h for h in enriched if h["line_id"] not in structural_lids]
    scores = [h["score"] for h in pool]
    pct_threshold = _percentile_threshold(scores, percentile=percentile)
    effective_threshold = max(float(min_score), pct_threshold)

    percentile_lids: set[int] = set()
    for h in pool:
        if h["score"] >= effective_threshold:
            percentile_lids.add(h["line_id"])

    final_lids = structural_lids | percentile_lids

    by_lid = {h["line_id"]: h for h in enriched}
    boundaries: List[BoundaryHeading] = []
    for lid in sorted(final_lids):
        h = by_lid[lid]
        source = "structural" if lid in structural_lids else "percentile"
        boundaries.append(
            BoundaryHeading(
                line_id=lid,
                text=h["text"],
                page_number=h["page_number"],
                score=h["score"],
                source=source,
                signals=h["signals"],
            )
        )

    stats = BoundarySelectionStats(
        total_validated_headings=total_validated,
        structural_count=len(structural_lids),
        percentile_count=len(percentile_lids),
        final_boundary_count=len(boundaries),
        percentile_used=float(percentile),
        min_score_used=int(min_score),
        score_threshold_used=float(effective_threshold),
    )
    return boundaries, stats

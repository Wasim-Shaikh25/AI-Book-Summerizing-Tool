"""Shared source-vs-generated overlap scoring for rewrite and quality audit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict

from src.shared import config
from src.shared.text_grounding import (
    ENUM_TITLE_LINE_RE as _ENUM_TITLE_LINE_RE,
    is_low_grounding as _is_low_grounding,
    real_content_chars as _real_content_chars,
)

_STOPWORDS = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "will",
        "shall",
        "section",
        "article",
        "articles",
        "which",
        "their",
        "there",
        "these",
        "those",
        "when",
        "where",
        "what",
        "into",
        "about",
    }
)

_FIDELITY_STRICT_PREFIX = (
    "Stay strictly within the provided source. "
    "Do not include facts from previous or next sections.\n\n"
)

def _tokens(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-zA-Z]{4,}", (text or "").lower())
        if w not in _STOPWORDS
    }


def source_real_content_chars(source: str) -> int:
    """Letters in the source excluding enumerated title-list lines (index/contents pages)."""
    return _real_content_chars(source)


def resolve_min_grounding_chars(explicit: int | None = None) -> int:
    """Minimum real (non-list) source characters for a section to be rewritable as prose."""
    if explicit is not None:
        return max(0, int(explicit))
    raw = getattr(config, "REWRITE_MIN_GROUNDING_CHARS", 160)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 160


def source_is_low_grounding(
    source: str,
    *,
    min_chars: int | None = None,
    enum_ratio: float = 0.6,
    min_lines: int = 3,
) -> bool:
    """True when source is an index/contents-style title list or has too little real text.

    Such sections give the model nothing to ground on, so it expands from prior
    knowledge. Detection is purely structural (enumeration ratio + letter count);
    it carries no subject-specific vocabulary.
    """
    return _is_low_grounding(
        source,
        min_chars=resolve_min_grounding_chars(min_chars),
        enum_ratio=enum_ratio,
        min_lines=min_lines,
    )


def section_overlap_score(*, source: str, generated: str) -> float:
    """Keyword overlap ratio: share of source content tokens present in generated text."""
    a, b = _tokens(source), _tokens(generated)
    if not a:
        return 1.0 if (generated or "").strip() else 0.0
    return len(a & b) / len(a)


def resolve_fidelity_min_overlap(explicit: float | None = None) -> float:
    if explicit is not None:
        return max(0.0, min(1.0, float(explicit)))
    raw = getattr(config, "REWRITE_FIDELITY_MIN_OVERLAP", 0.30)
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.30


def needs_regeneration(score: float, *, min_overlap: float | None = None) -> bool:
    threshold = resolve_fidelity_min_overlap(min_overlap)
    return score < threshold


def fidelity_strict_prompt_prefix() -> str:
    return _FIDELITY_STRICT_PREFIX


@dataclass
class RewriteFidelityStats:
    drift_regenerated: int = 0
    low_grounding_sections: int = 0
    attempts_per_section: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "drift_regenerated": self.drift_regenerated,
            "low_grounding_sections": self.low_grounding_sections,
            "attempts_per_section": dict(self.attempts_per_section),
        }


_last_fidelity_stats = RewriteFidelityStats()


def get_last_fidelity_stats() -> RewriteFidelityStats:
    return _last_fidelity_stats


def reset_fidelity_stats() -> RewriteFidelityStats:
    global _last_fidelity_stats
    _last_fidelity_stats = RewriteFidelityStats()
    return _last_fidelity_stats

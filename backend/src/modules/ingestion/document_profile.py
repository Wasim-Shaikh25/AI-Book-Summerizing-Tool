"""Measured document character profile — subject-agnostic tuning knobs."""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.shared.models import NormalizedLine

_ENUMERATED_LINE_RE = re.compile(
    r"^(?:\d+\.\s|\([A-Za-z0-9]{1,4}\)\s|[A-Z]\.\s)",
)
_PROSE_LINE_RE = re.compile(r".*\.\s*$")


@dataclass(frozen=True)
class DocumentProfileSettings:
    short_body_chars: int = 400
    base_min_section_body_chars: int = 200
    base_rewrite_overlap_chars: int = 600
    base_rewrite_max_tokens: int = 1800
    base_median_section_body_chars: int = 1200
    base_rewrite_max_source_chars: int = 6000


@dataclass(frozen=True)
class DocumentCharacterProfile:
    page_count: int
    line_count: int

    heading_density: float
    median_section_body_chars: int
    short_section_ratio: float
    prose_paragraph_ratio: float
    enumerated_clause_ratio: float
    avg_line_length: float
    title_token_median: int

    min_section_body_chars: int
    rewrite_max_source_chars: int
    rewrite_overlap_chars: int
    rewrite_max_tokens: int
    enforce_single_topic_prompt: bool
    require_strict_heading_match: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentCharacterProfile":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def resolve_document_profile_settings() -> DocumentProfileSettings:
    from src import config

    return DocumentProfileSettings(
        short_body_chars=int(getattr(config, "DOCUMENT_PROFILE_SHORT_BODY_CHARS", 400) or 400),
        base_min_section_body_chars=int(
            getattr(config, "DOCUMENT_PROFILE_BASE_MIN_SECTION_BODY_CHARS", 200) or 200
        ),
        base_rewrite_overlap_chars=int(
            getattr(config, "DOCUMENT_PROFILE_BASE_REWRITE_OVERLAP_CHARS", 600) or 600
        ),
        base_rewrite_max_tokens=int(
            getattr(config, "DOCUMENT_PROFILE_BASE_REWRITE_MAX_TOKENS", 1800) or 1800
        ),
        base_median_section_body_chars=int(
            getattr(config, "DOCUMENT_PROFILE_BASE_MEDIAN_SECTION_BODY_CHARS", 1200) or 1200
        ),
        base_rewrite_max_source_chars=int(
            getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000
        ),
    )


def _line_text_by_id(lines: Sequence[NormalizedLine]) -> Dict[int, str]:
    return {int(ln.line_id): str(ln.text or "") for ln in lines if getattr(ln, "line_id", None) is not None}


def _section_body_chars(
    start_line_id: int,
    end_line_id: Optional[int],
    line_text: Dict[int, str],
) -> int:
    if end_line_id is None:
        keys = [lid for lid in line_text if lid > start_line_id]
    else:
        keys = [lid for lid in line_text if start_line_id < lid < end_line_id]
    return sum(len(line_text.get(lid, "")) for lid in sorted(keys))


def _derive_knobs(
    *,
    heading_density: float,
    median_section_body_chars: int,
    short_section_ratio: float,
    prose_paragraph_ratio: float,
    enumerated_clause_ratio: float,
    title_token_median: int,
    settings: DocumentProfileSettings,
) -> Dict[str, Any]:
    density_factor = _clamp(heading_density / 1.0, 0.3, 3.0)
    brevity_factor = max(0.0, 1.0 - short_section_ratio)
    prose_factor = max(0.0, min(1.0, prose_paragraph_ratio))

    min_section_body_chars = max(
        20,
        round(settings.base_min_section_body_chars * brevity_factor * (1.0 / density_factor)),
    )
    rewrite_overlap_chars = max(
        0,
        round(settings.base_rewrite_overlap_chars * brevity_factor * prose_factor),
    )
    base_median = max(1, settings.base_median_section_body_chars)
    rewrite_max_tokens = int(
        _clamp(
            round(settings.base_rewrite_max_tokens * (median_section_body_chars / base_median)),
            400,
            settings.base_rewrite_max_tokens,
        )
    )
    enforce_single_topic_prompt = short_section_ratio > 0.5 or enumerated_clause_ratio > 0.4
    require_strict_heading_match = title_token_median <= 6 or heading_density > 1.0

    return {
        "min_section_body_chars": min_section_body_chars,
        "rewrite_max_source_chars": settings.base_rewrite_max_source_chars,
        "rewrite_overlap_chars": rewrite_overlap_chars,
        "rewrite_max_tokens": rewrite_max_tokens,
        "enforce_single_topic_prompt": enforce_single_topic_prompt,
        "require_strict_heading_match": require_strict_heading_match,
    }


def compute_document_profile(
    lines: Sequence[NormalizedLine],
    headings: Sequence[Dict[str, Any]],
    *,
    settings: Optional[DocumentProfileSettings] = None,
) -> DocumentCharacterProfile:
    """Compute a measured profile from normalized lines and accepted headings."""
    settings = settings or resolve_document_profile_settings()
    line_text = _line_text_by_id(lines)
    line_count = len(line_text)
    pages = {
        int(ln.page_number)
        for ln in lines
        if getattr(ln, "page_number", None) is not None and not getattr(ln, "is_noise", False)
    }
    page_count = max(pages) if pages else 0

    sorted_heads = sorted(
        [h for h in headings if isinstance(h.get("line_id"), int)],
        key=lambda x: int(x["line_id"]),
    )
    heading_count = len(sorted_heads)
    heading_density = (heading_count / page_count) if page_count > 0 else 0.0

    body_sizes: List[int] = []
    for i, head in enumerate(sorted_heads):
        lid = int(head["line_id"])
        nxt = int(sorted_heads[i + 1]["line_id"]) if i + 1 < len(sorted_heads) else None
        body_sizes.append(_section_body_chars(lid, nxt, line_text))

    median_body = int(statistics.median(body_sizes)) if body_sizes else 0
    short_body = settings.short_body_chars
    short_section_ratio = (
        sum(1 for size in body_sizes if size < short_body) / len(body_sizes) if body_sizes else 0.0
    )

    content_lines = [
        str(ln.text or "").strip()
        for ln in lines
        if str(ln.text or "").strip() and not getattr(ln, "is_noise", False)
    ]
    prose_count = sum(
        1 for text in content_lines if _PROSE_LINE_RE.match(text) and len(text.split()) >= 8
    )
    prose_paragraph_ratio = (prose_count / len(content_lines)) if content_lines else 0.0

    enum_count = sum(1 for text in content_lines if _ENUMERATED_LINE_RE.match(text))
    enumerated_clause_ratio = (enum_count / len(content_lines)) if content_lines else 0.0

    avg_line_length = (
        statistics.mean(len(text) for text in content_lines) if content_lines else 0.0
    )

    title_tokens = [len(str(h.get("text") or "").split()) for h in sorted_heads if h.get("text")]
    title_token_median = int(statistics.median(title_tokens)) if title_tokens else 0

    knobs = _derive_knobs(
        heading_density=heading_density,
        median_section_body_chars=median_body,
        short_section_ratio=short_section_ratio,
        prose_paragraph_ratio=prose_paragraph_ratio,
        enumerated_clause_ratio=enumerated_clause_ratio,
        title_token_median=title_token_median,
        settings=settings,
    )

    return DocumentCharacterProfile(
        page_count=page_count,
        line_count=line_count,
        heading_density=round(heading_density, 4),
        median_section_body_chars=median_body,
        short_section_ratio=round(short_section_ratio, 4),
        prose_paragraph_ratio=round(prose_paragraph_ratio, 4),
        enumerated_clause_ratio=round(enumerated_clause_ratio, 4),
        avg_line_length=round(avg_line_length, 2),
        title_token_median=title_token_median,
        **knobs,
    )


def load_document_profile(run_dir: Path | str) -> Optional[DocumentCharacterProfile]:
    """Load profile artifact from a pipeline run directory."""
    from src.modules.pipeline.stage_registry import STAGE_DOCUMENT_PROFILE, resolve_existing_artifact

    path = resolve_existing_artifact(run_dir, STAGE_DOCUMENT_PROFILE)
    if path is None or not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        payload = raw.get("payload")
        if payload is None and "items" in raw and isinstance(raw["items"], dict):
            payload = raw["items"]
        if payload is None and all(k in raw for k in DocumentCharacterProfile.__dataclass_fields__):
            payload = raw
    else:
        payload = None
    if not isinstance(payload, dict):
        return None
    return DocumentCharacterProfile.from_dict(payload)

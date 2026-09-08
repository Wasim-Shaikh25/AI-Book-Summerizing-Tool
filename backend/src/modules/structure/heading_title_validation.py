"""Shared heading title validation — deterministic rules only."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.shared.english_text import contains_english_letters, filter_english_heading, is_primarily_english
from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry, is_sentence_like_title
from src.modules.structure.final_structuring.signal_extractor import CITATION_RE

logger = logging.getLogger(__name__)

_CITATION_FRAGMENT_RE = re.compile(
    r"^\d{4}\s+NOC\b|"
    r"^\(\s*A\.?\s*I\.?\s*R\.?|"
    r"^[A-Z][a-z]+,\s*[-–—]?\s*A\.?\s*I\.?\s*R\b|"
    r"\bvs\.?\s+[A-Z]|"
    r"\bv\.\s+[A-Z][a-z]|"
    r"\bAIR\s+\d{4}\b|"
    r"\bSCC\b|\bSC\s+\d{4}\b|"
    r"\bPMID\s*:?\s*\d+|\bdoi\s*:\s*\S+|"
    r"\bFig(?:ure)?\.?\s*\d+|\bTable\s+\d+",
    re.I,
)
_CASE_INDEX_RE = re.compile(r"^case\s+no\.?\s*\d+", re.I)
_STRONG_HEADING_RE = re.compile(
    r"^(?:chapter\s+\d+|part\s+[IVXLC\d]+|"
    r"[IVXLC]+\.\s+[A-Z]|"
    r"[A-H]\.\s+[A-Z]|"
    r"FUNDAMENTAL\s+|CONSTITUTION|ARTICLE\s+\d+)",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_exempt_study_heading(title: str) -> bool:
    """Headings that look like prose triggers but are valid textbook section titles."""
    t = _norm(title)
    if re.match(r"^[IVXLC]+\.\s+[A-Z]", t, re.I):
        return True
    if re.search(r"\(\s*Arts?\.|\(\s*Art\.|\(\s*S\.\s*\d", t, re.I) and len(t.split()) <= 18:
        return True
    if t.endswith("?") and len(t.split()) <= 18:
        return True
    if re.match(r"^[A-H]\.\s+[A-Z]", t, re.I):
        return True
    return False


def is_citation_fragment_title(title: str) -> bool:
    t = _norm(title)
    if not t:
        return True
    if is_exempt_study_heading(t):
        return False
    if _CASE_INDEX_RE.match(t):
        return False
    if re.search(r"\bv\.\s+[A-Z][a-z]", t):
        return True
    if re.search(r"\bvs\.?\s+[A-Z]", t, re.I):
        return True
    if _CITATION_FRAGMENT_RE.search(t):
        return True
    if t.endswith(")") and not re.search(r"\(\s*Art|\(\d{4}\)\s*$", t, re.I):
        if re.search(r"^\(\s*A\.?\s*I\.?\s*R|^\d{4}\s+NOC", t, re.I):
            return True
        words = t.split()
        if len(words) <= 8 and re.search(r"\bNOC\b|\bMad\.|\bS\.?\s*C\.?\s*\d", t, re.I):
            return True
    if CITATION_RE.search(t) and len(t.split()) <= 14:
        if re.search(r"\bAIR\b|\bSCC\b|\bPMID\b|\bdoi\b|\bFig", t, re.I):
            return True
    return False


def is_strong_section_heading(title: str) -> bool:
    t = _norm(title)
    if not t or is_citation_fragment_title(t) or is_sentence_like_title(t):
        return False
    if _STRONG_HEADING_RE.search(t):
        return True
    if re.search(r"\(\s*Art", t, re.I) and len(t) >= 20 and not t.endswith("?"):
        return True
    if t.isupper() and len(t.split()) >= 2:
        return True
    return False


def rule_reject_reason(
    title: str,
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Optional[str]:
    t = _norm(title)
    if not t:
        return "empty"
    if registry and registry.is_banned_text(t):
        return "banned"
    if is_sentence_like_title(t) and not is_exempt_study_heading(t):
        return "sentence_like"
    if is_citation_fragment_title(t):
        return "citation_fragment"
    if not contains_english_letters(t) or not is_primarily_english(t):
        return "non_english"
    if filter_english_heading(t) is None:
        return "non_english"
    if len(t) > 110:
        return "too_long"
    return None


def assess_heading_title(
    title: str,
    *,
    preview: str = "",
    parent_heading: str = "",
    registry: Optional[DroppedHeadingRegistry] = None,
    **_: Any,
) -> Tuple[bool, Optional[str], str]:
    """Return (keep, reject_reason, method). Preview/parent are accepted for API compat."""
    del preview, parent_heading
    t = _norm(title)
    reason = rule_reject_reason(t, registry=registry)
    if reason:
        return False, reason, "rule"
    return True, None, "keep"


def _line_text_by_id(lines: Sequence[Any]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for ln in lines:
        lid = getattr(ln, "line_id", None) if not isinstance(ln, dict) else ln.get("line_id")
        if isinstance(lid, int):
            text = getattr(ln, "text", "") if not isinstance(ln, dict) else ln.get("text", "")
            out[lid] = str(text or "")
    return out


def body_preview_for_heading(
    heading: Dict[str, Any],
    *,
    ordered_headings: Sequence[Dict[str, Any]],
    line_text: Dict[int, str],
    max_chars: int = 240,
) -> str:
    """Body text after this heading until the next heading."""
    lid = heading.get("line_id")
    if not isinstance(lid, int):
        return ""
    lids = sorted(
        int(h["line_id"])
        for h in ordered_headings
        if isinstance(h.get("line_id"), int)
    )
    if lid not in lids:
        return ""
    idx = lids.index(lid)
    next_lid = lids[idx + 1] if idx + 1 < len(lids) else None
    start = lid + 1
    end = (next_lid - 1) if isinstance(next_lid, int) else max(line_text.keys(), default=lid)
    if end < start:
        return ""
    parts: List[str] = []
    for line_id in range(start, end + 1):
        t = (line_text.get(line_id) or "").strip()
        if t:
            parts.append(t)
    body = _norm(" ".join(parts))
    return body[:max_chars]


def filter_validated_headings(
    headings: Sequence[Dict[str, Any]],
    *,
    lines: Sequence[Any],
    registry: Optional[DroppedHeadingRegistry] = None,
    **_: Any,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Drop invalid headings before 15a/15d section division."""
    registry = registry or DroppedHeadingRegistry()
    ordered = sorted(
        [dict(h) for h in headings if isinstance(h.get("line_id"), int)],
        key=lambda h: int(h["line_id"]),
    )
    line_text = _line_text_by_id(lines)

    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    parent = ""
    stats = {
        "input_count": len(ordered),
        "kept_count": 0,
        "dropped_count": 0,
        "rule_rejected": 0,
    }

    for h in ordered:
        title = _norm(str(h.get("text") or ""))
        preview = body_preview_for_heading(h, ordered_headings=ordered, line_text=line_text)
        keep, reason, method = assess_heading_title(
            title,
            preview=preview,
            parent_heading=parent,
            registry=registry,
        )
        if keep:
            kept.append(h)
            parent = title
            stats["kept_count"] += 1
            continue

        stats["dropped_count"] += 1
        if method == "rule":
            stats["rule_rejected"] += 1

        lid = h.get("line_id")
        registry.register(line_id=lid if isinstance(lid, int) else None, text=title)
        dropped.append(
            {
                "line_id": lid,
                "text": title,
                "action": "drop_title_validation",
                "reason": reason,
                "method": method,
                "preview_used": preview[:120],
                "parent_heading": parent[:80],
            }
        )

    return kept, dropped, stats

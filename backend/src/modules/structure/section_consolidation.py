"""Universal post-hierarchy consolidation — merge thin / structural sections."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

from src.modules.generation.rewrite_validation import normalize_heading
from src.modules.structure.dropped_heading_registry import (
    is_acceptable_study_title,
    is_generic_study_title,
    is_noisy_fragment_heading,
    is_outline_heading,
)
from src.modules.structure.final_structuring.book_assembler import (
    _looks_like_structural_heading,
    _merge_two_sections,
    _section_body_chars,
)
from src.shared import config

_NUMBERED_TITLE_RE = re.compile(
    r"^(?:(?:section|art\.?|article|rule|§|part)\s*[\dIVXLC]+|\d{1,4}\.)",
    re.I,
)
_LOW_VALUE_RE = re.compile(
    r"^(illustrations?|explanation\.?|note\.?|classification\b|definition\.?|"
    r"punishments?\.?|examples?|explanation\.?\s*[-–—]?\s*)$",
    re.I,
)
_PUNISHMENT_FRAGMENT_RE = re.compile(
    r"^(?:imprisonment|fine|community service|death|life).{0,40}\.$",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def consolidation_enabled() -> bool:
    return bool(getattr(config, "SECTION_CONSOLIDATION_ENABLED", True))


def _min_body_chars() -> int:
    return int(getattr(config, "SECTION_CONSOLIDATION_MIN_CHARS", 200) or 200)


def _max_merged_chars() -> int:
    return int(getattr(config, "SECTION_CONSOLIDATION_MAX_CHARS", 12000) or 12000)


def is_low_value_heading(text: str) -> bool:
    """Heading that should not stand alone as an exported study topic."""
    t = _norm(text)
    if not t:
        return True
    if _looks_like_structural_heading(t):
        return True
    if is_noisy_fragment_heading(t):
        return True
    from src.modules.structure.dropped_heading_registry import is_incomplete_pdf_heading

    if is_incomplete_pdf_heading(t):
        return True
    if is_outline_heading(t):
        return True
    if is_generic_study_title(t):
        return True
    if _LOW_VALUE_RE.match(t):
        return True
    if t.lower().startswith("section topic (p."):
        return True
    if _PUNISHMENT_FRAGMENT_RE.match(t) and len(t.split()) <= 12:
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    if letters.isupper() and len(letters) >= 8 and len(t.split()) <= 12:
        return True
    if re.match(r"^OF\s+[A-Z]", t) and letters.isupper() and len(letters) >= 6:
        return True
    upper_ratio = sum(1 for c in letters if c.isupper()) / max(len(letters), 1)
    if upper_ratio >= 0.85 and len(letters) >= 10 and len(t.split()) <= 10:
        return True
    return False


def _title_score(text: str) -> int:
    t = _norm(text)
    if not t or not is_acceptable_study_title(t):
        return -100
    score = min(len(t), 80)
    if _NUMBERED_TITLE_RE.match(t):
        score += 120
    if is_low_value_heading(t):
        score -= 80
    if is_generic_study_title(t):
        score -= 40
    return score


def _best_merged_title(left: str, right: str) -> str:
    candidates = [_norm(left), _norm(right)]
    substantive = [c for c in candidates if c and not is_low_value_heading(c)]
    pool = substantive or [c for c in candidates if c]
    if not pool:
        return candidates[0] or candidates[1] or ""
    return max(pool, key=_title_score)[:120]


def _should_merge_pair(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    left_page = left.get("page_number")
    right_page = right.get("page_number")
    if left_page is not None and right_page is not None and int(right_page) < int(left_page):
        return False
    left_chars = _section_body_chars(left)
    right_chars = _section_body_chars(right)
    combined = left_chars + right_chars
    if combined > _max_merged_chars():
        return False
    if combined < _min_body_chars():
        return True
    left_heading = str(left.get("heading") or "")
    right_heading = str(right.get("heading") or "")
    if is_low_value_heading(left_heading) or is_low_value_heading(right_heading):
        return True
    if left_chars < _min_body_chars() // 2 or right_chars < _min_body_chars() // 2:
        return True
    return False


def _merge_pair(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two sections; richer body becomes primary, best title wins."""
    a = copy.deepcopy(left)
    b = copy.deepcopy(right)
    if _section_body_chars(b) > _section_body_chars(a):
        a, b = b, a
    merged = _merge_two_sections(a, b)
    merged["heading"] = _best_merged_title(str(a.get("heading") or ""), str(b.get("heading") or ""))
    return merged


def _is_droppable(sec: Dict[str, Any]) -> bool:
    if _section_body_chars(sec) >= _min_body_chars() // 4:
        return False
    heading = str(sec.get("heading") or "")
    return is_low_value_heading(heading) and not (sec.get("subheadings") or [])


def consolidate_chapter_sections(sections: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Merge adjacent thin/low-value sections within one chapter."""
    if not sections:
        return [], 0

    work = [copy.deepcopy(sec) for sec in sections]
    merges = 0
    changed = True
    while changed:
        changed = False
        out: List[Dict[str, Any]] = []
        i = 0
        while i < len(work):
            current = work[i]
            if i + 1 < len(work) and _should_merge_pair(current, work[i + 1]):
                current = _merge_pair(current, work[i + 1])
                i += 2
                merges += 1
                changed = True
            else:
                i += 1
            out.append(current)
        work = out

    final: List[Dict[str, Any]] = []
    for sec in work:
        if _is_droppable(sec):
            continue
        final.append(sec)
    return final, merges


def _renumber_section_ids(hierarchy: Dict[str, Any]) -> None:
    n = 0
    for ch in hierarchy.get("chapters") or []:
        new_secs: List[Dict[str, Any]] = []
        for sec in ch.get("sections") or []:
            n += 1
            sec = dict(sec)
            sec["section_id"] = f"S{n}"
            new_secs.append(sec)
        ch["sections"] = new_secs


def consolidate_hierarchy(hierarchy: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Merge thin adjacent sections in every chapter; renumber section IDs."""
    if not consolidation_enabled():
        return hierarchy, 0

    out = copy.deepcopy(hierarchy)
    total_merges = 0
    for ch in out.get("chapters") or []:
        sections = list(ch.get("sections") or [])
        consolidated, merges = consolidate_chapter_sections(sections)
        ch["sections"] = consolidated
        total_merges += merges

    _renumber_section_ids(out)
    meta = dict(out.get("meta") or {})
    meta["section_consolidation_merges"] = total_merges
    meta["section_consolidation_method"] = "thin_structural_merge"
    out["meta"] = meta
    return out, total_merges

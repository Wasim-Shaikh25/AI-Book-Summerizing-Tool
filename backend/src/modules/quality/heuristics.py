"""Deterministic heuristics for notes / heading quality."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.dropped_heading_registry import (
    is_generic_study_title,
    is_noisy_fragment_heading,
    is_sentence_like_title,
    is_structural_partition_heading,
    is_syllabus_heading,
)

_SYLLABUS_BODY_RE = re.compile(
    r"(course\s+objectives?|course\s+outcomes?|learning\s+outcomes?|"
    r"syllabus|reading\s+list|recommended\s+readings?)\b",
    re.I,
)
_MODULE_BODY_RE = re.compile(r"\b(module|unit)\s+\d+\b", re.I)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def heading_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def classify_heading(title: str) -> str:
    if not title:
        return "empty"
    if is_sentence_like_title(title):
        return "prose_not_topic"
    if is_weak_section_heading(title):
        return "weak_fragment"
    if is_noisy_fragment_heading(title):
        return "noisy_fragment"
    from src.modules.structure.dropped_heading_registry import is_incomplete_pdf_heading

    if is_incomplete_pdf_heading(title):
        return "incomplete_fragment"
    if is_structural_partition_heading(title):
        return "structural_partition"
    from src.modules.structure.dropped_heading_registry import is_statute_prose_heading

    if is_statute_prose_heading(title):
        return "statute_prose"
    if is_generic_study_title(title):
        return "generic_study"
    if is_syllabus_heading(title):
        return "syllabus_heading"
    if re.search(r"\bA\.?\s*I\.?\s*R\.?", title, re.I) and ")" in title:
        return "case_line"
    if re.search(r"^\d{4}\s+NOC", title, re.I):
        return "case_line"
    if re.search(r"\(\s*p\.\s*\d+\)\s*$", title):
        return "disambiguation_noise"
    if title.endswith("?") and len(title.split()) > 6:
        return "question_prose"
    if len(title) > 95:
        return "too_long"
    if len(title.split()) > 12:
        return "too_many_words"
    return "looks_ok"


def detect_syllabus_noise_in_body(body: str) -> List[str]:
    if not (body or "").strip():
        return []
    flags: List[str] = []
    low = body.lower()
    if _SYLLABUS_BODY_RE.search(body):
        flags.append("syllabus_admin")
    if _MODULE_BODY_RE.search(body):
        flags.append("module_unit_ref")
    if "also cover:" in low:
        flags.append("also_cover_checklist")
    for line in body.splitlines():
        if is_syllabus_heading(line.strip()):
            flags.append("syllabus_heading_line")
            break
    return flags


def chapter_mirrors_first_section(chapter_heading: str, first_section_heading: str, *, threshold: float = 0.72) -> bool:
    """True when chapter title is essentially the same as its first section (parent-as-subtopic)."""
    ch = (chapter_heading or "").strip()
    sec = (first_section_heading or "").strip()
    if not ch or not sec:
        return False
    if norm(ch) == norm(sec):
        return True
    return heading_sim(ch, sec) >= threshold


def find_parent_mirror_chapters(chapters: Sequence[Dict[str, Any]], *, threshold: float = 0.72) -> List[str]:
    out: List[str] = []
    for ch in chapters:
        ch_name = str(ch.get("heading") or "")
        secs = list(ch.get("sections") or [])
        if not secs:
            continue
        first = str(secs[0].get("heading") or "")
        if chapter_mirrors_first_section(ch_name, first, threshold=threshold):
            out.append(f"{ch_name[:50]} ≈ {first[:50]}")
    return out


def compute_verdict_scores(
    *,
    mapped_count: int,
    total_sections: int,
    inversions: int,
    dup_chapter_count: int,
    avg_overlap: float,
    repeated_pairs: int,
    weak_heading_count: int,
    title_noise_count: int,
    syllabus_body_hits: int,
    pdf_match_failures: int,
    parent_mirror_count: int = 0,
    line_audit_fail_sections: int = 0,
    line_audit_warn_sections: int = 0,
    heading_acceptance_failed: int = 0,
    heading_export_violations: int = 0,
    short_notes: int = 0,
) -> Dict[str, str]:
    scores: Dict[str, str] = {}
    ratio = mapped_count / max(total_sections, 1)
    scores["coverage"] = "PASS" if ratio >= 0.98 else ("OK" if ratio >= 0.9 else "WARN")
    if ratio >= 0.98 and short_notes <= 3 and avg_overlap >= 0.30:
        scores["completeness"] = "PASS"
    elif ratio >= 0.90 and short_notes <= 8:
        scores["completeness"] = "OK"
    else:
        scores["completeness"] = "WARN"
    scores["sequence"] = "PASS" if inversions <= 5 else ("OK" if inversions <= 25 else "WARN")
    scores["hierarchy"] = "PASS" if dup_chapter_count == 0 else ("OK" if dup_chapter_count <= 2 else "WARN")
    scores["fidelity"] = "PASS" if avg_overlap >= 0.35 else ("OK" if avg_overlap >= 0.22 else "WARN")
    scores["repetition"] = "PASS" if repeated_pairs <= 5 else ("OK" if repeated_pairs <= 15 else "WARN")
    naming_bad = weak_heading_count + title_noise_count
    scores["naming"] = "PASS" if naming_bad <= 5 else ("OK" if naming_bad <= 15 else "WARN")
    scores["syllabus_noise"] = "PASS" if syllabus_body_hits == 0 else ("OK" if syllabus_body_hits <= 3 else "WARN")
    scores["pdf_match"] = "PASS" if pdf_match_failures <= 3 else ("OK" if pdf_match_failures <= 10 else "WARN")
    scores["parent_mirror"] = "PASS" if parent_mirror_count == 0 else ("OK" if parent_mirror_count <= 2 else "WARN")
    if heading_acceptance_failed == 0 and heading_export_violations == 0:
        scores["heading_acceptance"] = "PASS"
    elif heading_export_violations <= 2 and heading_acceptance_failed <= 2:
        scores["heading_acceptance"] = "OK"
    else:
        scores["heading_acceptance"] = "WARN"
    if line_audit_fail_sections == 0 and line_audit_warn_sections == 0:
        scores["line_quality"] = "PASS"
    elif line_audit_fail_sections == 0 and line_audit_warn_sections <= 5:
        scores["line_quality"] = "OK"
    elif line_audit_fail_sections <= 3:
        scores["line_quality"] = "WARN"
    else:
        scores["line_quality"] = "WARN"
    priority_dims = ("completeness", "heading_acceptance", "coverage", "line_quality")
    priority_warn = any(scores.get(d) == "WARN" for d in priority_dims)
    warn_dims = sum(1 for k, v in scores.items() if v == "WARN")
    ok_dims = sum(1 for v in scores.values() if v == "OK")
    if warn_dims == 0 and ok_dims <= 4 and not priority_warn:
        scores["overall"] = "PASS"
    elif warn_dims <= 3 and not (
        scores.get("completeness") == "WARN"
        or scores.get("heading_acceptance") == "WARN"
        or scores.get("line_quality") == "WARN"
    ):
        scores["overall"] = "OK"
    else:
        scores["overall"] = "WARN"
    return scores

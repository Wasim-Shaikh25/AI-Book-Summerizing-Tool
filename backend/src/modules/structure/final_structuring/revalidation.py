"""
Stage 15b — selective revalidation (cloud LLM audit of flagged segments).

Fast pass classifies all doubted segments; only suspicious items are sent to a
small instruct model for a second opinion.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from .models.segment_llm_classifier import get_revalidation_classifier

# Methods that are most error-prone and worth revalidating.
_RISKY_METHODS = frozenset({
    "syllabus_at_first_toc_page",
    "page_position_fallback",
    "first_toc_section_span",
})

_EXAM_MARKS_RE = re.compile(r"\b\d+\s*marks?\b", re.I)
_CHAPTER_HEADING_RE = re.compile(r"^chapter\s+\d+\s*$", re.I)


def select_revalidation_candidates(
    draft_segments: List[Dict[str, Any]],
    *,
    confidence_threshold: float = 0.85,
    max_candidates: int = 40,
    first_body_line_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Pick segments that should be audited by the fast LLM.

    Returns list of {segment_id, draft_result, reason_selected}.
    """
    selected: List[Dict[str, Any]] = []

    for seg in draft_segments:
        method = str(seg.get("method") or "")
        conf = float(seg.get("confidence") or 0.0)
        resolved = str(seg.get("resolved_as") or "")
        line_ids = seg.get("line_ids") or []
        seg_min = min(line_ids) if line_ids else 0
        heading = (seg.get("heading_text") or "").strip()

        reasons: List[str] = []

        if method in _RISKY_METHODS:
            reasons.append(f"method:{method}")
        # Low-confidence checks should be conservative; we avoid auditing
        # stable methods like miniLM/msmarco unless another risk reason exists.
        if conf < confidence_threshold and method in _RISKY_METHODS:
            reasons.append(f"low_confidence:{conf:.2f}")

        # Integrated chapter openers mis-tagged as toc
        if (
            resolved == "toc"
            and first_body_line_id is not None
            and seg_min >= first_body_line_id
            and _is_integrated_chapter_opener(heading, seg)
        ):
            reasons.append("integrated_chapter_opener")

        # Short exam-question style headings
        if resolved == "real_content" and _EXAM_MARKS_RE.search(heading):
            reasons.append("exam_marks_in_heading")

        if not reasons:
            continue

        selected.append({
            "segment_id": seg.get("segment_id"),
            "draft": seg,
            "selection_reasons": reasons,
        })

    # Cap cost — highest priority first
    priority = {
        "integrated_chapter_opener": 0,
        "method:syllabus_at_first_toc_page": 1,
        "method:page_position_fallback": 2,
        "low_confidence": 3,
    }

    def _prio(item: Dict[str, Any]) -> int:
        for r in item.get("selection_reasons") or []:
            for key, val in priority.items():
                if key in r:
                    return val
        return 9

    selected.sort(key=_prio)
    return selected[:max_candidates]


def _is_integrated_chapter_opener(heading: str, seg: Dict[str, Any]) -> bool:
    combined = heading + " " + str(seg.get("heading_text") or "")
    if re.search(r"questions\s+(?:for|of)\s+this\s+chapter", combined, re.I):
        return True
    if re.search(r"disability\s+to\s+sue", combined, re.I):
        return True
    if re.match(r"^Chapter\s+\d+", heading, re.I):
        return True
    return False


def _has_explicit_toc_evidence(reason: str) -> bool:
    r = (reason or "").lower()
    return any(
        token in r for token in (
            "dot leader",
            "page number",
            "index",
            "table of contents",
            "toc list",
        )
    )


def _local_context(
    line_ids: List[int],
    line_by_id: Dict[int, Dict[str, Any]],
    *,
    window: int = 12,
) -> str:
    if not line_ids:
        return ""
    lo = max(0, min(line_ids) - window)
    hi = max(line_ids) + window
    parts: List[str] = []
    for lid in range(lo, hi + 1):
        if lid not in line_by_id:
            continue
        t = (line_by_id[lid].get("text") or "").strip()
        if t:
            pg = line_by_id[lid].get("page_number")
            mark = ">>>" if lid in line_ids else "   "
            parts.append(f"{mark} L{lid} p{pg}: {t[:120]}")
    return "\n".join(parts[-35:])


def revalidate_selected_candidates(
    candidates: List[Dict[str, Any]],
    line_by_id: Dict[int, Dict[str, Any]],
    *,
    neighbor_headings: Optional[List[str]] = None,
    first_body_line_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Run fast LLM on selected items only. Returns audit log entries.
    """
    classifier = get_revalidation_classifier()
    if not classifier.enabled:
        return []

    audits: List[Dict[str, Any]] = []
    neighbors = neighbor_headings or []

    for item in candidates:
        seg = item.get("draft") or {}
        line_ids = [int(x) for x in (seg.get("line_ids") or [])]
        context = _local_context(line_ids, line_by_id)
        result = classifier.revalidate(
            heading_text=seg.get("heading_text") or "",
            current_label=str(seg.get("resolved_as") or ""),
            current_method=str(seg.get("method") or ""),
            context_text=context,
            neighbor_headings=neighbors[:15],
            page_start=int(seg.get("page_start") or 0),
            page_end=int(seg.get("page_end") or 0),
        )
        entry: Dict[str, Any] = {
            "segment_id": seg.get("segment_id"),
            "selection_reasons": item.get("selection_reasons"),
            "draft_resolved_as": seg.get("resolved_as"),
            "draft_method": seg.get("method"),
            "draft_confidence": seg.get("confidence"),
        }
        if result is None:
            entry["revalidated"] = False
            audits.append(entry)
            continue

        entry["revalidated"] = True
        entry["corrected_label"] = result.get("category")
        entry["confidence"] = result.get("confidence")
        entry["keep_heading"] = result.get("keep_heading", True)
        entry["reason"] = result.get("reason", "")
        audits.append(entry)

        # Apply override on segment with strict guardrails to avoid
        # over-correcting real chapter content into metadata/toc.
        new_label = result.get("category")
        if new_label and new_label in ("metadata", "toc", "real_content"):
            draft_label = str(seg.get("resolved_as") or "")
            llm_conf = float(result.get("confidence", 0.0) or 0.0)
            seg_min = min(line_ids) if line_ids else 0

            # Guard 1: Do not demote chapter-body content unless the model is
            # very sure. Small 0.5B models can be noisy here.
            if draft_label == "real_content" and new_label in ("metadata", "toc") and llm_conf < 0.93:
                entry["override_applied"] = False
                entry["override_skipped_reason"] = "low_confidence_demote"
                continue

            # Guard 2: Never demote content that starts at/after first body line.
            # This protects integrated chapter material from false metadata flips.
            if (
                draft_label == "real_content"
                and new_label in ("metadata", "toc")
                and first_body_line_id is not None
                and seg_min >= first_body_line_id
            ):
                entry["override_applied"] = False
                entry["override_skipped_reason"] = "chapter_body_protected"
                continue

            # Guard 3: For chapter headings in body region, do not keep/force TOC
            # unless the model provides explicit TOC evidence in reason text.
            heading_txt = str(seg.get("heading_text") or "").strip()
            if (
                first_body_line_id is not None
                and seg_min >= first_body_line_id
                and _CHAPTER_HEADING_RE.match(heading_txt)
                and new_label == "toc"
                and not _has_explicit_toc_evidence(str(result.get("reason") or ""))
            ):
                new_label = "real_content"
                entry["corrected_label"] = "real_content"
                entry["override_adjusted_reason"] = "chapter_heading_without_toc_evidence"

            seg["resolved_as"] = new_label
            seg["method"] = f"revalidate_{classifier.backend}"
            seg["confidence"] = float(result.get("confidence", 0.8))
            seg["revalidation_reason"] = result.get("reason", "")
            seg["draft_resolved_as"] = entry["draft_resolved_as"]
            if result.get("keep_heading") is False:
                seg["demote_heading"] = True
            entry["override_applied"] = True

    return audits


def apply_revalidation(
    draft_segments: List[Dict[str, Any]],
    line_by_id: Dict[int, Dict[str, Any]],
    *,
    neighbor_headings: Optional[List[str]] = None,
    confidence_threshold: float = 0.85,
    max_candidates: int = 40,
    first_body_line_id: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Select → revalidate → return (updated segments, audit log).
    """
    candidates = select_revalidation_candidates(
        draft_segments,
        confidence_threshold=confidence_threshold,
        max_candidates=max_candidates,
        first_body_line_id=first_body_line_id,
    )
    if not candidates:
        return draft_segments, []

    classifier = get_revalidation_classifier()
    if not classifier.enabled:
        print(
            f"[Stage 15b] {len(candidates)} segment(s) flagged for revalidation "
            f"but LLM backend disabled (set LLM_PROVIDER to OPENAI or OPENROUTER)."
        )
        return draft_segments, []

    print(f"[Stage 15b] Revalidating {len(candidates)} selected segment(s) via {classifier.backend}...")
    audits = revalidate_selected_candidates(
        candidates,
        line_by_id,
        neighbor_headings=neighbor_headings,
        first_body_line_id=first_body_line_id,
    )
    changed = sum(
        1 for a in audits
        if a.get("revalidated")
        and a.get("override_applied", True)
        and a.get("corrected_label") != a.get("draft_resolved_as")
    )
    print(f"[Stage 15b] Revalidation changed {changed}/{len(candidates)} segment(s).")
    return draft_segments, audits

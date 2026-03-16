from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from .logging.pipeline_logger import PipelineLogger
from .models import HeadingCandidate, NormalizedLine


def _paragraph_after_heading(lines: Sequence[NormalizedLine], heading_end_line: int, *, max_lines: int = 12) -> str:
    """
    Best-effort: return a preview of the paragraph-like text immediately after a heading.
    Used only for TOC false-positive safeguards.
    """
    start = max(0, heading_end_line + 1)
    parts: List[str] = []
    for i in range(start, min(len(lines), start + max_lines)):
        t = lines[i].text
        if t is None:
            continue
        # Stop early if a big vertical gap suggests a new section break
        if getattr(lines[i], "large_gap", False) and i > start:
            break
        parts.append(t)
    return "\n".join(parts)


def resolve_toc_sections(
    headings: Sequence[HeadingCandidate],
    *,
    lines: Sequence[NormalizedLine],
    logger: PipelineLogger,
) -> List[HeadingCandidate]:
    """
    Removes TOC blocks according to Gemini TOC signals:
      - Identify consecutive headings where is_toc==true
      - If there are 3+ consecutive, remove the whole block

    Safeguards:
      - If valid headings < 2: keep everything
      - If after the heading there's a large paragraph (>200 chars), override is_toc=false (keep)
      - Conservative: never remove the first heading
    """
    if len(headings) == 0:
        logger.write_stage("toc_section_eval", [{"decision": "no_headings", "reason": "no headings"}])
        return []

    valid_count = sum(1 for h in headings if h.is_valid is True)
    if valid_count < 2:
        logger.write_stage(
            "toc_section_eval",
            [
                {
                    "toc_block_id": "toc_000",
                    "start_heading_id": headings[0].id if headings else None,
                    "end_heading_id": headings[-1].id if headings else None,
                    "heading_ids": [h.id for h in headings],
                    "combined_preview": "",
                    "decision": "keep_all",
                    "reason": "valid_headings<2 safeguard",
                    "removed_headings": [],
                    "kept_headings": [h.id for h in headings],
                    "model": None,
                    "latency_ms": None,
                }
            ],
        )
        return list(headings)

    removed_ids: List[str] = []
    kept_ids: List[str] = []
    removed_entries: List[Dict[str, Any]] = []

    # NOTE: We remove TOC *blocks* of 3+ consecutive is_toc==true (not individual TOC headings).
    # This matches "section only" removal semantics.

    # Pass 1: remove 3+ consecutive where is_toc==true (section removal)
    adjusted = list(headings)
    kept_ids = [h.id for h in adjusted]

    # Only applies to items not already removed (kept_ids is the current kept universe)
    i = 0
    kept_set = set(kept_ids)
    while i < len(adjusted):
        h = adjusted[i]
        if h.id not in kept_set:
            i += 1
            continue
        is_toc_block_item = h.is_toc is True
        if not is_toc_block_item:
            i += 1
            continue

        j = i
        block: List[HeadingCandidate] = []
        while j < len(adjusted):
            hh = adjusted[j]
            if hh.id in kept_set and (hh.is_toc is True):
                block.append(hh)
                j += 1
                continue
            break

        if len(block) >= 3:
            for b in block:
                if b.id in kept_set:
                    kept_set.remove(b.id)
                removed_ids.append(b.id)
                removed_entries.append(
                    {
                        "removed_id": b.id,
                        "reason": "toc_block_3plus",
                        "is_valid": b.is_valid,
                        "is_toc": b.is_toc,
                    }
                )
                logger.record_decision(
                    b.id,
                    stage="toc_section_resolver",
                    decision="removed",
                    metadata={"reason": "toc_block_3plus"},
                )

        # IMPORTANT: always advance past the scanned block; otherwise we rescan the same TOC streak.
        i = j

    # Pass 2: apply paragraph safeguard ONLY to items that were kept after TOC section removal
    kept: List[HeadingCandidate] = []
    for h in adjusted:
        if h.id not in kept_set:
            continue
        if h.is_toc is True:
            preview = _paragraph_after_heading(lines, h.end_line)
            if len(preview) > 200:
                updated = HeadingCandidate(
                    id=h.id,
                    text=h.text,
                    start_line=h.start_line,
                    end_line=h.end_line,
                    before_context=list(h.before_context),
                    after_context=list(h.after_context),
                    full_context_preview=h.full_context_preview,
                    is_valid=h.is_valid,
                    valid_reason=h.valid_reason,
                    is_toc=False,
                    toc_reason="safeguard:followed_by_large_paragraph",
                )
                kept.append(updated)
                logger.record_decision(
                    h.id,
                    stage="toc_safeguard",
                    decision="override_is_toc_false",
                    metadata={"reason": "followed_by_large_paragraph", "chars": len(preview)},
                )
                continue
        kept.append(h)
    logger.write_stage(
        "toc_section_eval",
        [
            {
                "toc_block_id": "toc_001",
                "start_heading_id": headings[0].id if headings else None,
                "end_heading_id": headings[-1].id if headings else None,
                "heading_ids": [h.id for h in headings],
                "combined_preview": "",
                "decision": "remove_block" if removed_entries else "keep",
                "reason": "toc_block_3plus" if removed_entries else "no_toc_block_removed",
                "removed_headings": [e.get("removed_id") for e in removed_entries],
                "kept_headings": [h.id for h in kept],
                "model": None,
                "latency_ms": None,
            }
        ],
    )
    return kept

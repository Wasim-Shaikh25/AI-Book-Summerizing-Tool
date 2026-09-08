"""Stage 15g — late safety net on chapter hierarchy (early validation is s13)."""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry, title_from_subheadings
from src.modules.structure.final_structuring.heading_cleanup import (
    _disambiguate_section_heading,
    _ultimate_heading_map,
)
from src.modules.structure.heading_title_validation import (
    _norm,
    assess_heading_title,
    rule_reject_reason,
)

logger = logging.getLogger(__name__)


def _preview_text(row: Dict[str, Any]) -> str:
    frag = row.get("fragment") or {}
    return _norm(str(frag.get("preview") or ""))[:240]


def _fix_rejected_title(
    sec: Dict[str, Any],
    *,
    ultimate_heading: str,
    chapter_heading: str,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Tuple[str, str]:
    subs = list(sec.get("subheadings") or [])
    from_sub = title_from_subheadings(subs, registry=registry)
    if from_sub:
        return from_sub, "subheading"

    cleaned = _norm(ultimate_heading)
    if cleaned and not rule_reject_reason(cleaned, registry=registry) and not is_weak_section_heading(cleaned):
        return cleaned, "ultimate"

    fallback = _disambiguate_section_heading(
        ultimate_heading or cleaned or chapter_heading,
        chapter_heading=chapter_heading,
        preview="",
        page_number=sec.get("page_number"),
        occurrence=1,
        subheadings=subs,
        registry=registry,
    )
    return fallback, "disambiguate"


def validate_chapter_hierarchy(
    chapter_hierarchy: Dict[str, Any],
    *,
    ultimate_sections: Optional[Sequence[Dict[str, Any]]] = None,
    dropped_registry: Optional[DroppedHeadingRegistry] = None,
    **_: Any,
) -> Dict[str, Any]:
    """Stage 15g — safety net after 15f; primary validation runs at s13 before 15d."""
    out = copy.deepcopy(chapter_hierarchy)
    chapters = list(out.get("chapters") or [])
    if not chapters:
        return out

    from src.modules.structure.final_structuring.heading_cleanup import (
        disambiguate_duplicate_chapter_titles,
        merge_duplicate_named_chapters,
        sanitize_merged_section_titles,
    )
    from src.modules.structure.final_structuring.chapter_placement import enforce_chapter_structure
    from src.modules.structure.final_structuring.subheading_refinement import fix_verbose_section_titles

    chapters, _ = merge_duplicate_named_chapters(chapters)
    sanitize_merged_section_titles(chapters)
    fix_verbose_section_titles({"chapters": chapters})
    disambiguate_duplicate_chapter_titles(chapters)
    out["chapters"] = chapters

    registry = dropped_registry or DroppedHeadingRegistry()
    ultimate_by_sid = _ultimate_heading_map(ultimate_sections or [])

    rule_rejected = fixed = kept = 0
    audit: List[Dict[str, Any]] = []

    for ch in chapters:
        chapter_heading = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            title = _norm(str(sec.get("heading") or ""))
            preview = _preview_text(sec)
            ultimate = ultimate_by_sid.get(sid, title)
            keep, reason, method = assess_heading_title(
                title,
                preview=preview,
                parent_heading=chapter_heading,
                registry=registry,
            )
            if keep:
                kept += 1
                continue

            if method == "rule":
                rule_rejected += 1

            new_title, fix_method = _fix_rejected_title(
                sec,
                ultimate_heading=ultimate,
                chapter_heading=chapter_heading,
                registry=registry,
            )
            if registry and not registry.is_allowed_title(new_title):
                new_title = _disambiguate_section_heading(
                    ultimate or chapter_heading,
                    chapter_heading=chapter_heading,
                    preview="",
                    page_number=sec.get("page_number"),
                    occurrence=1,
                    subheadings=sec.get("subheadings"),
                    registry=registry,
                )
                fix_method = "disambiguate_fallback"

            audit.append(
                {
                    "section_id": sid,
                    "old_heading": title[:120],
                    "new_heading": new_title[:120],
                    "reason": reason,
                    "fix_method": fix_method,
                    "validation_method": method,
                    "preview_used": preview[:120],
                }
            )
            sec["heading"] = new_title
            fixed += 1

    meta = dict(out.get("meta") or {})
    meta.update(
        {
            "title_validation_enabled": True,
            "title_validation_stage": "15g_late_safety_net",
            "title_validation_rule_rejected": rule_rejected,
            "title_validation_kept": kept,
            "title_validation_fixed": fixed,
            "title_validation_audit_sample": audit[:40],
        }
    )
    out["meta"] = meta
    out["chapters"] = chapters
    if audit:
        out["title_validation_audit"] = audit
    out, enforce_stats = enforce_chapter_structure(out)
    meta = dict(out.get("meta") or {})
    meta["hierarchy_enforce_stats"] = enforce_stats
    out["meta"] = meta
    return out

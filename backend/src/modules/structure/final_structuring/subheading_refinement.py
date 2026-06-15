"""Stage 15i — refine chapter, section, and subheading titles (single heading pass before rewrite)."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from src.modules.generation.rewrite_validation import is_weak_section_heading, normalize_heading
from src.modules.structure.dropped_heading_registry import (
    is_noisy_fragment_heading,
    is_structural_partition_heading,
    is_syllabus_heading,
    partition_heading_to_study_title,
    title_from_subheadings,
)
from src.modules.structure.final_structuring.chapter_placement import universal_clean_heading
from src.modules.structure.final_structuring.heading_title_engine import (
    _filter_candidates,
    _range_title,
    pick_chapter_title,
    pick_section_title,
    pick_subheading_title,
    title_from_fragment_preview,
)
from src.modules.quality.heuristics import chapter_mirrors_first_section
from src.shared import config

logger = logging.getLogger(__name__)

_BULLET_PREFIX = re.compile(r"^[•\-\*·]\s+")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _fragment_chars(row: Dict[str, Any]) -> int:
    frag = row.get("fragment") or {}
    return int(frag.get("chars") or 0)


def _sub_preview(row: Dict[str, Any]) -> str:
    frag = row.get("fragment") or {}
    return _norm(str(frag.get("preview") or ""))[:240]


def refine_subheading_title(
    sub: Dict[str, Any],
    *,
    section_heading: str,
    chapter_heading: str = "",
    sibling_labels: Optional[Sequence[str]] = None,
    use_transformers: bool = True,
) -> str:
    """Clean one subheading — rules + MiniLM."""
    raw = _norm(str(sub.get("heading") or ""))
    if raw:
        raw = _BULLET_PREFIX.sub("", raw).strip()
    if not raw:
        return raw
    return pick_subheading_title(
        sub,
        section_heading=section_heading,
        chapter_heading=chapter_heading,
        sibling_labels=sibling_labels,
        use_transformers=use_transformers,
    )


def _dedupe_subheadings(subheadings: List[Dict[str, Any]]) -> int:
    """Drop duplicate subheadings within a section; keep the richest fragment."""
    if len(subheadings) < 2:
        return 0
    best_by_key: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    removed = 0
    for sub in subheadings:
        label = _norm(str(sub.get("heading") or ""))
        key = normalize_heading(label) or f"__empty_{id(sub)}"
        if key not in best_by_key:
            best_by_key[key] = sub
            order.append(key)
            continue
        removed += 1
        existing = best_by_key[key]
        if _fragment_chars(sub) > _fragment_chars(existing):
            best_by_key[key] = sub
    if removed:
        subheadings[:] = [best_by_key[k] for k in order if k in best_by_key]
    return removed


def _drop_noise_subheadings(subheadings: List[Dict[str, Any]]) -> int:
    """Remove subheadings with no usable label and no source text."""
    kept: List[Dict[str, Any]] = []
    dropped = 0
    for sub in subheadings:
        label = _norm(str(sub.get("heading") or ""))
        chars = _fragment_chars(sub)
        preview = _sub_preview(sub)
        if not label and not preview and chars < 20:
            dropped += 1
            continue
        if is_weak_section_heading(label) and chars < 40 and not preview:
            dropped += 1
            continue
        if is_structural_partition_heading(label):
            dropped += 1
            continue
        kept.append(sub)
    if dropped:
        subheadings[:] = kept
    return dropped


def refine_section_headings_from_context(
    hierarchy: Dict[str, Any],
    *,
    use_transformers: bool = True,
) -> int:
    """Improve weak section titles using chapter + subheading context."""
    changed = 0
    for ch in hierarchy.get("chapters") or []:
        ch_name = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            old = _norm(str(sec.get("heading") or ""))
            new = pick_section_title(
                sec,
                chapter_heading=ch_name,
                use_transformers=use_transformers,
            )
            if new != old:
                sec["heading"] = new
                changed += 1
    return changed


def refine_subheadings_in_hierarchy(
    hierarchy: Dict[str, Any],
    *,
    use_transformers: bool = True,
) -> int:
    """Clean every subheading label under each section."""
    changed = 0
    for ch in hierarchy.get("chapters") or []:
        ch_name = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            sec_name = _norm(str(sec.get("heading") or ""))
            subs = list(sec.get("subheadings") or [])
            sibling_labels = [_norm(str(s.get("heading") or "")) for s in subs]
            for sub in subs:
                old = _norm(str(sub.get("heading") or ""))
                new = refine_subheading_title(
                    sub,
                    section_heading=sec_name,
                    chapter_heading=ch_name,
                    sibling_labels=sibling_labels,
                    use_transformers=use_transformers,
                )
                if new != old:
                    sub["heading"] = new
                    changed += 1
    return changed


def refine_chapter_titles(hierarchy: Dict[str, Any]) -> int:
    """Fix chapter (#) titles that are too narrow for their grouped sections."""
    from src.modules.structure.final_structuring.chapter_placement import (
        refine_broad_chapter_titles,
        universal_clean_heading,
    )

    book_title = _norm(
        str(
            hierarchy.get("book_title")
            or (hierarchy.get("meta") or {}).get("book_title")
            or ""
        )
    )
    chapters = list(hierarchy.get("chapters") or [])
    changed = refine_broad_chapter_titles(chapters)
    for ch in chapters:
        sections = list(ch.get("sections") or [])
        old = _norm(str(ch.get("heading") or ""))
        if is_structural_partition_heading(old):
            normalized = partition_heading_to_study_title(old)
            if normalized and normalize_heading(normalized) != normalize_heading(old):
                ch["heading"] = normalized[:120]
                changed += 1
                old = normalized
        if is_syllabus_heading(old) and book_title:
            ch["heading"] = book_title[:120]
            changed += 1
            continue
        if len(sections) < 2:
            new = universal_clean_heading(old, use_transformers=False)
            if new != old:
                ch["heading"] = new
                changed += 1
            continue
        first = _norm(str(sections[0].get("heading") or ""))
        mirror = (
            normalize_heading(old) == normalize_heading(first)
            or is_syllabus_heading(old)
            or chapter_mirrors_first_section(old, first)
        )
        if mirror:
            inferred = pick_chapter_title(sections, book_title=book_title)
            if inferred and chapter_mirrors_first_section(inferred, first):
                ranged = _range_title(
                    _filter_candidates([_norm(str(s.get("heading") or "")) for s in sections])
                )
                if ranged:
                    inferred = ranged
            if inferred and normalize_heading(inferred) != normalize_heading(old):
                ch["heading"] = inferred[:120]
                changed += 1
    hierarchy["chapters"] = chapters
    return changed


def fix_verbose_section_titles(hierarchy: Dict[str, Any]) -> int:
    """Shorten sentence-like / fragment PDF headings using preview-derived labels."""
    from src.modules.quality.heuristics import classify_heading
    from src.modules.structure.final_structuring.heading_cleanup import _rule_clean_heading, _preview_text

    changed = 0
    for ch in hierarchy.get("chapters") or []:
        ch_name = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            old = _norm(str(sec.get("heading") or ""))
            if not old:
                continue
            cleaned = _rule_clean_heading(
                old,
                preview=_preview_text(sec),
                subheadings=sec.get("subheadings"),
            )
            if cleaned and cleaned != old and classify_heading(cleaned) == "looks_ok":
                sec["heading"] = cleaned[:120]
                changed += 1
                old = cleaned
            cls = classify_heading(old)
            if cls in {"looks_ok", "empty"}:
                continue
            # Prefer a clean subheading label over raw body-preview prose.
            new = title_from_subheadings(sec.get("subheadings"))
            if not new or classify_heading(new) not in {"looks_ok"}:
                new = title_from_fragment_preview(sec)
            if not new or classify_heading(new) not in {"looks_ok"}:
                new = pick_section_title(sec, chapter_heading=ch_name, use_transformers=False)
            if not new or new == old or classify_heading(new) not in {"looks_ok"}:
                continue
            sec["heading"] = new[:120]
            changed += 1
    return changed


def fix_placeholder_section_titles(hierarchy: Dict[str, Any]) -> int:
    """Replace 'Section topic (p. N)' and other noisy placeholders with preview-derived titles."""
    changed = 0
    for ch in hierarchy.get("chapters") or []:
        ch_name = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            old = _norm(str(sec.get("heading") or ""))
            if not is_noisy_fragment_heading(old):
                continue
            new = pick_section_title(sec, chapter_heading=ch_name, use_transformers=True)
            if is_noisy_fragment_heading(new):
                new = title_from_fragment_preview(sec)
            if new and new != old and not is_noisy_fragment_heading(new):
                sec["heading"] = new[:120]
                changed += 1
    return changed


def fix_parent_mirror_chapters(hierarchy: Dict[str, Any]) -> int:
    """Ensure chapter titles are broader than their first section (avoid parent-as-subtopic)."""
    from src.modules.structure.dropped_heading_registry import (
        is_acceptable_study_title,
        partition_heading_to_study_title,
    )
    from src.modules.structure.final_structuring.heading_title_engine import (
        pick_chapter_title,
        pick_section_title,
        title_from_fragment_preview,
    )

    changed = 0
    for ch in hierarchy.get("chapters") or []:
        sections = list(ch.get("sections") or [])
        if not sections:
            continue
        old = _norm(str(ch.get("heading") or ""))
        first = _norm(str(sections[0].get("heading") or ""))
        if not old or not first:
            continue

        if len(sections) == 1 and chapter_mirrors_first_section(old, first):
            sec = sections[0]
            new_title = pick_section_title(sec, chapter_heading=old, use_transformers=False)
            if not new_title or chapter_mirrors_first_section(new_title, first):
                new_title = title_from_fragment_preview(sec) or partition_heading_to_study_title(first)
            if new_title and not chapter_mirrors_first_section(new_title, first):
                ch["heading"] = new_title[:120]
                changed += 1
            subs = list(sec.get("subheadings") or [])
            if subs:
                promoted: List[Dict[str, Any]] = []
                for sub in subs:
                    promoted.append(
                        {
                            "section_id": str(sub.get("topic_id") or sub.get("section_id") or ""),
                            "heading": _norm(str(sub.get("heading") or "")),
                            "page_number": sub.get("page_number") or sec.get("page_number"),
                            "fragment": dict(sub.get("fragment") or {}),
                            "subheadings": [],
                        }
                    )
                ch["sections"] = [row for row in promoted if row.get("heading")]
            continue

        if not chapter_mirrors_first_section(old, first):
            continue

        new_title = ""
        if len(sections) > 1:
            new_title = pick_chapter_title(sections[1:], book_title="")
        if not new_title or chapter_mirrors_first_section(new_title, first):
            new_title = pick_chapter_title(sections, book_title="")
        if chapter_mirrors_first_section(new_title, first):
            for sec in sections[1:4]:
                alt = _norm(str(sec.get("heading") or ""))
                if alt and not chapter_mirrors_first_section(alt, first) and is_acceptable_study_title(alt):
                    new_title = alt
                    break

        if not new_title or chapter_mirrors_first_section(new_title, first):
            distinct = []
            for sec in sections:
                h = _norm(str(sec.get("heading") or ""))
                if h and h not in distinct:
                    distinct.append(h)
            if len(distinct) >= 2:
                new_title = f"{distinct[0]} to {distinct[-1]}"[:120]

        if (
            new_title
            and not chapter_mirrors_first_section(new_title, first)
            and normalize_heading(new_title) != normalize_heading(old)
        ):
            ch["heading"] = new_title[:120]
            changed += 1
    return changed


def fix_unacceptable_section_titles(
    hierarchy: Dict[str, Any],
    *,
    use_transformers: bool = True,
    lines: Optional[Sequence[Any]] = None,
    require_strict_heading_match: bool = False,
) -> int:
    """Force title repair when heading fails is_acceptable_study_title or classify_heading."""
    from src.modules.quality.heuristics import classify_heading
    from src.modules.structure.dropped_heading_registry import (
        is_acceptable_study_title,
        is_incomplete_pdf_heading,
        is_noisy_fragment_heading,
        is_structural_partition_heading,
    )
    from src.modules.structure.final_structuring.heading_title_engine import title_from_fragment_preview

    changed = 0
    for ch in hierarchy.get("chapters") or []:
        ch_name = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            old = _norm(str(sec.get("heading") or ""))
            if not old:
                continue
            cls = classify_heading(old)
            if (
                cls == "looks_ok"
                and is_acceptable_study_title(old)
                and not is_incomplete_pdf_heading(old)
                and not is_noisy_fragment_heading(old)
                and not is_structural_partition_heading(old)
            ):
                continue
            new = pick_section_title(
                sec,
                chapter_heading=ch_name,
                use_transformers=use_transformers,
                lines=lines,
                require_strict_heading_match=require_strict_heading_match,
            )
            if not is_acceptable_study_title(new):
                preview_title = title_from_fragment_preview(sec)
                if preview_title and is_acceptable_study_title(preview_title):
                    new = preview_title
            if new and new != old and is_acceptable_study_title(new):
                sec["heading"] = new[:120]
                changed += 1
    return changed


def run_heading_refinement(
    chapter_hierarchy: Dict[str, Any],
    *,
    lines: Optional[Sequence[Any]] = None,
    document_profile: Optional[Any] = None,
) -> Dict[str, Any]:
    """Stage 15i — all title fixes: chapters, sections, subheadings (before rewrite / 15g)."""
    if not getattr(config, "HEADING_REFINEMENT_ENABLED", True):
        return chapter_hierarchy

    from src.modules.structure.final_structuring.chapter_placement import apply_universal_heading_cleanup
    from src.modules.structure.final_structuring.heading_cleanup import sanitize_merged_section_titles

    out = copy.deepcopy(chapter_hierarchy)
    chapters = list(out.get("chapters") or [])
    use_transformers = bool(getattr(config, "HEADING_REFINEMENT_USE_TRANSFORMERS", True))
    require_strict = bool(
        document_profile and getattr(document_profile, "require_strict_heading_match", False)
    )

    merged_clean = sanitize_merged_section_titles(chapters)
    chapter_changes = refine_chapter_titles(out)

    deduped = dropped = section_changes = sub_changes = 0
    if getattr(config, "HEADING_REFINEMENT_DEDUPE", True):
        for ch in out.get("chapters") or []:
            for sec in ch.get("sections") or []:
                subs = list(sec.get("subheadings") or [])
                if subs:
                    deduped += _dedupe_subheadings(subs)
                    sec["subheadings"] = subs

    if getattr(config, "HEADING_REFINEMENT_DROP_EMPTY", True):
        for ch in out.get("chapters") or []:
            for sec in ch.get("sections") or []:
                subs = list(sec.get("subheadings") or [])
                if subs:
                    dropped += _drop_noise_subheadings(subs)
                    sec["subheadings"] = subs

    section_changes = refine_section_headings_from_context(out, use_transformers=use_transformers)
    sub_changes = refine_subheadings_in_hierarchy(out, use_transformers=use_transformers)
    placeholder_fixes = fix_placeholder_section_titles(out)
    mirror_fixes = fix_parent_mirror_chapters(out)
    cleanup_changes = apply_universal_heading_cleanup(out, use_transformers=use_transformers)

    from src.modules.structure.section_consolidation import consolidate_hierarchy

    out, consolidation_merges = consolidate_hierarchy(out)
    from src.modules.structure.final_structuring.heading_cleanup import (
        disambiguate_duplicate_section_headings,
        sanitize_merged_section_titles,
    )

    sanitize_merged_section_titles(list(out.get("chapters") or []))
    verbose_fixes = fix_verbose_section_titles(out)
    unacceptable_fixes = fix_unacceptable_section_titles(
        out,
        use_transformers=use_transformers,
        lines=lines,
        require_strict_heading_match=require_strict,
    )
    disambiguate_duplicate_section_headings(list(out.get("chapters") or []))
    from src.modules.structure.final_structuring.heading_cleanup import sanitize_hierarchy_headings

    sanitize_hierarchy_headings(out)

    from src.modules.structure.final_structuring.chapter_placement import enforce_chapter_structure

    out, enforce_stats = enforce_chapter_structure(out)
    meta = dict(out.get("meta") or {})
    meta.update(
        {
            "total_chapters": len(out.get("chapters") or []),
            "heading_refinement_method": "rules+minilm" if use_transformers else "rules",
            "heading_refinement_merged_title_cleanups": merged_clean,
            "heading_refinement_chapter_titles": chapter_changes,
            "heading_refinement_deduped": deduped,
            "heading_refinement_dropped": dropped,
            "heading_refinement_section_titles": section_changes,
            "heading_refinement_subheading_titles": sub_changes,
            "heading_refinement_placeholder_fixes": placeholder_fixes,
            "heading_refinement_parent_mirror_fixes": mirror_fixes,
            "heading_refinement_cleanup_pass": cleanup_changes,
            "heading_refinement_section_consolidation_merges": consolidation_merges,
            "heading_refinement_verbose_title_fixes": verbose_fixes,
            "heading_refinement_unacceptable_fixes": unacceptable_fixes,
            "hierarchy_enforce_stats": enforce_stats,
        }
    )
    out["meta"] = meta
    logger.info(
        "15i heading refinement: chapters=%s deduped=%s dropped=%s sections=%s subs=%s",
        chapter_changes,
        deduped,
        dropped,
        section_changes,
        sub_changes,
    )
    return out


# Backward-compatible alias
run_subheading_refinement = run_heading_refinement

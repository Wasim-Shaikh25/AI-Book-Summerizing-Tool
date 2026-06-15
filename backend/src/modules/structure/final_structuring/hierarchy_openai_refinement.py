"""Stage 15j — OpenAI hierarchy regroup, title correction, and noisy-title polish."""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from src.modules.structure.final_structuring.chapter_cohesion import (
    coalesce_regroup_assignments,
    consolidate_chapter_hierarchy,
)
from src.modules.structure.final_structuring.chapter_placement import enforce_chapter_structure
from src.shared import config

logger = logging.getLogger(__name__)

_REGROUP_SYSTEM = """You organize academic textbook sections into study chapters for exam notes.

Rules:
1) Group ALL related consecutive sections under ONE chapter (same legal theme: marriage, divorce, succession, fundamental rights, pollution acts, etc.).
2) Target 6-10 chapters for a ~50-section syllabus book. NEVER create more than 12 chapters.
3) Before starting a new chapter, ask: "Is the next section about the SAME major topic as the previous sections?" If yes, keep it in the same chapter.
4) Do NOT create a chapter with only 1-2 sections unless the heading is MODULE N, UNIT N, or PART N.
5) Combine thin tail chapters (probate, wills, misc) into the nearest related chapter when themes overlap.
6) Every section_id must appear exactly once, in original order.
7) Start a new chapter ONLY at MODULE/UNIT/PART boundaries or a clear shift (e.g. Muslim law → Parsi law, rights → DPSP).
8) Do not invent sections or change order.

Reply JSON only:
{"assignments":[{"section_id":"S1","chapter_title":"Introductory Topics","is_chapter_start":true}]}"""

_NAMES_SYSTEM = """You correct chapter, section, and subheading titles in a study-notes hierarchy.

Rules:
1) chapter_heading: specific legal topic covering ALL sections (e.g. "Sources and Schools of Muslim Law", NOT "Family Law I" or "Overview of...").
2) section_heading: the exact legal topic taught (e.g. "Meaning of Mahr", NOT "Overview of Family Law" or book/module labels).
3) subheading: short topic label (max 8 words). No essay phrases like "A Study of...".
4) Never use: "CHAPTER I:", "PART II", "OF OFFENCES…" ALL-CAPS partition lines, "Overview of X", "Family Law I/II", "Module N", book filename, or syllabus-only labels as section/subheading titles — those are chapter breaks only.
5) Use consistent title case study labels (e.g. "Preliminary", "Punishments", "Offences Against the State") — not raw PDF chunk headings.
6) Do not change section_id, topic_id, or hierarchy structure — titles only.
7) Use simple English suitable for exam revision.

Reply JSON only:
{"chapters":[{"chapter_id":"C1","heading":"Sources of Muslim Law","sections":[{"section_id":"S1","heading":"Shariat Application Act 1937","subheadings":[{"topic_id":"S1_T1","heading":"Course Objectives"}]}]}]}"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _flatten_sections(chapters: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for ch in chapters:
        for sec in ch.get("sections") or []:
            flat.append(dict(sec))
    return flat


def _parse_regroup_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\"assignments\"[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    items = data.get("assignments")
    if not isinstance(items, list):
        return None
    out: List[Dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("section_id") or "").strip()
        title = _norm(str(row.get("chapter_title") or ""))
        if not sid or not title:
            continue
        out.append(
            {
                "section_id": sid,
                "chapter_title": title[:120],
                "is_chapter_start": bool(row.get("is_chapter_start")),
            }
        )
    return out or None


def _parse_names_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\"chapters\"[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        return None
    return chapters


def _rebuild_from_assignments(
    sections: Sequence[Dict[str, Any]],
    assignments: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    from src.modules.structure.final_structuring.chapter_hierarchy_builder import _assignments_to_chapters

    return _assignments_to_chapters(sections, assignments)


def _compact_sections_for_regroup(sections: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sec in sections:
        subs = [
            _norm(str(s.get("heading") or ""))[:80]
            for s in (sec.get("subheadings") or [])[:6]
            if _norm(str(s.get("heading") or ""))
        ]
        rows.append(
            {
                "section_id": sec.get("section_id"),
                "heading": _norm(str(sec.get("heading") or ""))[:120],
                "page": sec.get("page_number"),
                "subheadings": subs,
            }
        )
    return rows


def _compact_hierarchy_for_names(chapters: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ch in chapters:
        ch_row: Dict[str, Any] = {
            "chapter_id": ch.get("chapter_id"),
            "heading": _norm(str(ch.get("heading") or ""))[:120],
            "sections": [],
        }
        for sec in ch.get("sections") or []:
            sec_row: Dict[str, Any] = {
                "section_id": sec.get("section_id"),
                "heading": _norm(str(sec.get("heading") or ""))[:120],
                "subheadings": [],
            }
            for sub in sec.get("subheadings") or []:
                sec_row["subheadings"].append(
                    {
                        "topic_id": sub.get("topic_id"),
                        "heading": _norm(str(sub.get("heading") or ""))[:100],
                    }
                )
            ch_row["sections"].append(sec_row)
        out.append(ch_row)
    return out


_POLISH_SYSTEM = """You fix noisy PDF-extracted headings into clear exam study titles.

Rules:
1) Use the preview text to infer the real legal topic taught.
2) chapter_heading: specific topic (never MODULE N, UNIT N, book filename, or ALL-CAPS subject label alone).
3) section_heading: concise topic (max 10 words). Never partial sentences, "(IPC", lone letters, or page artifacts.
4) subheading: short label (max 8 words) from the subtopic content.
5) Do not change section_id, topic_id, or hierarchy order — titles only.

Reply JSON only:
{"chapters":[{"chapter_id":"C1","heading":"Clean Chapter Title","sections":[{"section_id":"S1","heading":"Clean Section","subheadings":[{"topic_id":"S1_T1","heading":"Subtopic"}]}]}]}"""


def _openai_regroup_assignments(
    sections: Sequence[Dict[str, Any]],
    *,
    book_title: str = "",
    current_chapters: int = 0,
) -> Optional[List[Dict[str, Any]]]:
    from src.modules.pipeline.llm_chat_client import LlmChatClient
    from src.shared.llm_provider import is_cloud_chat_provider, resolve_stage_provider

    provider = resolve_stage_provider(
        str(getattr(config, "HIERARCHY_OPENAI_PROVIDER", "") or config.CHAPTER_HIERARCHY_LLM or "")
    )
    if not is_cloud_chat_provider(provider):
        return None

    client = LlmChatClient.from_config(temperature=0.1)
    target_max = int(getattr(config, "HIERARCHY_OPENAI_TARGET_MAX_CHAPTERS", 8) or 8)
    min_secs = int(getattr(config, "HIERARCHY_OPENAI_MIN_SECTIONS_PER_CHAPTER", 2) or 2)
    batch_size = int(getattr(config, "HIERARCHY_OPENAI_REGROUP_BATCH_SIZE", 22) or 22)

    if len(sections) <= batch_size:
        return _openai_regroup_batch(
            client,
            provider,
            sections,
            book_title=book_title,
            current_chapters=current_chapters,
            target_max=target_max,
            min_secs=min_secs,
            prior_chapters=[],
        )

    merged: List[Dict[str, Any]] = []
    prior_titles: List[str] = []
    for start in range(0, len(sections), batch_size):
        batch = sections[start : start + batch_size]
        parsed = _openai_regroup_batch(
            client,
            provider,
            batch,
            book_title=book_title,
            current_chapters=current_chapters,
            target_max=target_max,
            min_secs=min_secs,
            prior_chapters=prior_titles[-6:],
        )
        if not parsed:
            logger.warning("15j regroup batch failed at offset=%s", start)
            return None
        merged.extend(parsed)
        for row in parsed:
            if row.get("is_chapter_start"):
                prior_titles.append(str(row.get("chapter_title") or ""))

    expected = {str(s.get("section_id")) for s in sections}
    got = {str(r["section_id"]) for r in merged}
    if expected != got:
        logger.warning("15j regroup mismatch expected=%s got=%s", len(expected), len(got))
        return None
    return merged


def _openai_regroup_batch(
    client: Any,
    provider: str,
    sections: Sequence[Dict[str, Any]],
    *,
    book_title: str,
    current_chapters: int,
    target_max: int,
    min_secs: int,
    prior_chapters: Sequence[str],
) -> Optional[List[Dict[str, Any]]]:
    compact = _compact_sections_for_regroup(sections)
    user = json.dumps(
        {
            "book_title": book_title[:120],
            "current_chapter_count": current_chapters,
            "target_max_chapters": target_max,
            "min_sections_per_chapter": min_secs,
            "prior_chapters": list(prior_chapters),
            "sections": compact,
        },
        ensure_ascii=False,
    )
    raw = client.chat_with_provider(provider, system=_REGROUP_SYSTEM, user=user, max_tokens=4096)
    parsed = _parse_regroup_json(raw or "")
    if not parsed:
        return None
    expected = {str(s.get("section_id")) for s in sections}
    got = {str(r["section_id"]) for r in parsed}
    if expected != got:
        logger.warning("15j regroup batch mismatch expected=%s got=%s", len(expected), len(got))
        return None
    return parsed


def _compact_hierarchy_with_previews(chapters: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ch in chapters:
        ch_row: Dict[str, Any] = {
            "chapter_id": ch.get("chapter_id"),
            "heading": _norm(str(ch.get("heading") or ""))[:120],
            "sections": [],
        }
        for sec in ch.get("sections") or []:
            preview = _norm(str((sec.get("fragment") or {}).get("preview") or ""))[:200]
            sec_row: Dict[str, Any] = {
                "section_id": sec.get("section_id"),
                "heading": _norm(str(sec.get("heading") or ""))[:120],
                "preview": preview,
                "subheadings": [],
            }
            for sub in sec.get("subheadings") or []:
                sub_preview = _norm(str((sub.get("fragment") or {}).get("preview") or ""))[:120]
                sec_row["subheadings"].append(
                    {
                        "topic_id": sub.get("topic_id"),
                        "heading": _norm(str(sub.get("heading") or ""))[:100],
                        "preview": sub_preview,
                    }
                )
            ch_row["sections"].append(sec_row)
        out.append(ch_row)
    return out


def _openai_polish_noisy_titles(
    chapters: List[Dict[str, Any]],
    *,
    book_title: str = "",
    lines: Optional[Sequence[Any]] = None,
    require_strict_heading_match: bool = False,
) -> int:
    """Third OpenAI pass — fix MODULE/noisy/fragment headings using content previews."""
    from src.modules.pipeline.llm_chat_client import LlmChatClient
    from src.shared.llm_provider import is_cloud_chat_provider, resolve_stage_provider

    if not _hierarchy_needs_polish_pass(chapters, book_title=book_title):
        return 0

    provider = resolve_stage_provider(
        str(getattr(config, "HIERARCHY_OPENAI_PROVIDER", "") or config.CHAPTER_HIERARCHY_LLM or "")
    )
    if not is_cloud_chat_provider(provider):
        return 0

    client = LlmChatClient.from_config(temperature=0.1)
    compact = _compact_hierarchy_with_previews(chapters)
    user = json.dumps({"book_title": book_title[:120], "chapters": compact}, ensure_ascii=False)
    raw = client.chat_with_provider(provider, system=_POLISH_SYSTEM, user=user, max_tokens=6144)
    parsed = _parse_names_json(raw or "")
    if not parsed:
        return 0
    return _apply_name_corrections(
        chapters,
        parsed,
        book_title=book_title,
        lines=lines,
        require_strict_heading_match=require_strict_heading_match,
    )


def _refine_semantic_titles(chapters: List[Dict[str, Any]], *, book_title: str = "") -> int:
    """Replace generic module/overview labels with topic titles from section content."""
    from src.modules.structure.dropped_heading_registry import (
        is_generic_study_title,
        is_noisy_fragment_heading,
    )
    from src.modules.structure.final_structuring.heading_title_engine import (
        pick_chapter_title,
        pick_section_title,
    )

    changed = 0
    for ch in chapters:
        sections = list(ch.get("sections") or [])
        ch_name = _norm(str(ch.get("heading") or ""))
        if is_generic_study_title(ch_name, book_title=book_title) and len(sections) >= 1:
            inferred = pick_chapter_title(sections, book_title=book_title)
            if inferred and not is_generic_study_title(inferred, book_title=book_title):
                ch["heading"] = inferred[:120]
                changed += 1
                ch_name = inferred

        for sec in sections:
            old = _norm(str(sec.get("heading") or ""))
            if not is_generic_study_title(old, book_title=book_title) and not is_noisy_fragment_heading(old):
                continue
            new = pick_section_title(sec, chapter_heading=ch_name, use_transformers=False)
            if new and not is_generic_study_title(new, book_title=book_title):
                sec["heading"] = new[:120]
                changed += 1

    return changed


def _apply_name_corrections(
    chapters: List[Dict[str, Any]],
    name_rows: Sequence[Dict[str, Any]],
    *,
    book_title: str = "",
    lines: Optional[Sequence[Any]] = None,
    require_strict_heading_match: bool = False,
) -> int:
    from src.modules.structure.dropped_heading_registry import is_acceptable_study_title
    from src.modules.structure.final_structuring.title_pdf_anchor import accept_edited_title

    ch_by_id = {str(ch.get("chapter_id")): ch for ch in chapters}
    changed = 0

    for ch_row in name_rows:
        cid = str(ch_row.get("chapter_id") or "")
        ch = ch_by_id.get(cid)
        if ch is None:
            continue
        new_ch = _norm(str(ch_row.get("heading") or ""))
        if new_ch and is_acceptable_study_title(new_ch, book_title=book_title):
            old = _norm(str(ch.get("heading") or ""))
            gated = accept_edited_title(
                new_ch,
                old,
                lines=lines,
                page_number=(ch.get("sections") or [{}])[0].get("page_number") if ch.get("sections") else None,
                require_strict=require_strict_heading_match,
            )
            if gated != old:
                ch["heading"] = gated[:120]
                changed += 1

        sec_by_id = {str(s.get("section_id")): s for s in ch.get("sections") or []}
        for sec_row in ch_row.get("sections") or []:
            sid = str(sec_row.get("section_id") or "")
            sec = sec_by_id.get(sid)
            if sec is None:
                continue
            new_sec = _norm(str(sec_row.get("heading") or ""))
            if new_sec and is_acceptable_study_title(new_sec, book_title=book_title):
                old = _norm(str(sec.get("heading") or ""))
                gated = accept_edited_title(
                    new_sec,
                    old,
                    lines=lines,
                    page_number=sec.get("page_number"),
                    require_strict=require_strict_heading_match,
                )
                if gated != old:
                    sec["heading"] = gated[:120]
                    changed += 1

            sub_by_id = {str(s.get("topic_id")): s for s in sec.get("subheadings") or []}
            for sub_row in sec_row.get("subheadings") or []:
                tid = str(sub_row.get("topic_id") or "")
                sub = sub_by_id.get(tid)
                if sub is None:
                    continue
                new_sub = _norm(str(sub_row.get("heading") or ""))
                if new_sub and is_acceptable_study_title(new_sub, book_title=book_title):
                    old = _norm(str(sub.get("heading") or ""))
                    gated = accept_edited_title(
                        new_sub,
                        old,
                        lines=lines,
                        page_number=sec.get("page_number"),
                        require_strict=require_strict_heading_match,
                    )
                    if gated != old:
                        sub["heading"] = gated[:120]
                        changed += 1

    return changed


def _hierarchy_needs_regroup(
    chapters: Sequence[Dict[str, Any]],
    *,
    section_count: int = 0,
) -> bool:
    """True when rule+MiniLM chapter groups are not study-ready (15j regroup LLM needed).

    Skips the expensive batched regroup pass (~3–7 min on large acts) when local
    stages already produced a healthy chapter count and section distribution.
    """
    if not chapters:
        return False
    n = len(chapters)
    sizes = [len(ch.get("sections") or []) for ch in chapters]
    if not sizes or section_count <= 0:
        return n > 1
    max_sz = max(sizes)
    min_sz = min(sizes)
    avg = section_count / max(n, 1)
    target_max = int(getattr(config, "HIERARCHY_OPENAI_TARGET_MAX_CHAPTERS", 8) or 8)
    max_per_ch = int(getattr(config, "CHAPTER_PLACEMENT_MAX_SECTIONS_PER_CHAPTER", 12) or 12)

    # Collapsed mega-chapter — regroup helps split syllabus dumps.
    if n == 1 and section_count > max(20, target_max * 3):
        return True
    # Oversized chapter — placement may have missed a split.
    if max_sz > max_per_ch + 2:
        return True
    # Too many thin chapters — cloud regroup may merge.
    if n > 14:
        return True
    # Healthy local hierarchy — skip regroup (saves most 15j tokens/time).
    if 3 <= n <= 12 and avg >= 4.0 and max_sz <= max_per_ch:
        return False
    if n <= 2 and section_count > 18:
        return True
    return n > target_max + 5


def _hierarchy_needs_polish_pass(
    chapters: Sequence[Dict[str, Any]], *, book_title: str = ""
) -> bool:
    """True when noisy/MODULE/generic titles need the 15j polish LLM pass."""
    from src.modules.structure.dropped_heading_registry import (
        is_generic_study_title,
        is_noisy_fragment_heading,
    )

    for ch in chapters:
        if is_generic_study_title(str(ch.get("heading") or ""), book_title=book_title):
            return True
        for sec in ch.get("sections") or []:
            h = str(sec.get("heading") or "")
            if is_noisy_fragment_heading(h) or is_generic_study_title(h, book_title=book_title):
                return True
            for sub in sec.get("subheadings") or []:
                sh = str(sub.get("heading") or "")
                if is_noisy_fragment_heading(sh) or is_generic_study_title(sh, book_title=book_title):
                    return True
    return False


def hierarchy_needs_cloud_refinement(
    chapter_hierarchy: Dict[str, Any],
) -> bool:
    """True if any 15j cloud pass (regroup, names, or polish) is still required."""
    if not getattr(config, "HIERARCHY_OPENAI_ENABLED", True):
        return False
    auto_skip = getattr(config, "HIERARCHY_OPENAI_AUTO_SKIP", True)
    if not auto_skip:
        return True

    chapters = list(chapter_hierarchy.get("chapters") or [])
    if not chapters:
        return False
    book_title = _norm(
        str(chapter_hierarchy.get("book_title") or (chapter_hierarchy.get("meta") or {}).get("book_title") or "")
    )
    sections = _flatten_sections(chapters)
    return (
        _hierarchy_needs_regroup(chapters, section_count=len(sections))
        or _hierarchy_titles_need_cloud_cleanup(chapters, book_title=book_title)
        or _hierarchy_needs_polish_pass(chapters, book_title=book_title)
    )


def _hierarchy_titles_need_cloud_cleanup(
    chapters: Sequence[Dict[str, Any]], *, book_title: str = ""
) -> bool:
    """True if any chapter/section/subheading title is not already a clean study label.

    Lets stage 15j skip the LLM names pass entirely when deterministic stages have
    already produced clean titles (cost reduction, no quality risk — we only skip
    when *every* title is acceptable and free of partition/prose/generic/noise).
    """
    from src.modules.structure.dropped_heading_registry import (
        is_acceptable_study_title,
        is_generic_study_title,
        is_noisy_fragment_heading,
        is_sentence_like_title,
        is_statute_prose_heading,
        is_structural_partition_heading,
    )

    def _bad(text: str) -> bool:
        t = _norm(text)
        if not t:
            return False
        return (
            not is_acceptable_study_title(t, book_title=book_title)
            or is_generic_study_title(t, book_title=book_title)
            or is_noisy_fragment_heading(t)
            or is_structural_partition_heading(t)
            or is_sentence_like_title(t)
            or is_statute_prose_heading(t)
        )

    for ch in chapters:
        if _bad(str(ch.get("heading") or "")):
            return True
        for sec in ch.get("sections") or []:
            if _bad(str(sec.get("heading") or "")):
                return True
            for sub in sec.get("subheadings") or []:
                if _bad(str(sub.get("heading") or "")):
                    return True
    return False


def _openai_name_corrections(
    chapters: Sequence[Dict[str, Any]],
    *,
    book_title: str = "",
    lines: Optional[Sequence[Any]] = None,
    require_strict_heading_match: bool = False,
) -> int:
    from src.modules.pipeline.llm_chat_client import LlmChatClient
    from src.shared.llm_provider import is_cloud_chat_provider, resolve_stage_provider

    provider = resolve_stage_provider(
        str(getattr(config, "HIERARCHY_OPENAI_PROVIDER", "") or config.CHAPTER_HIERARCHY_LLM or "")
    )
    if not is_cloud_chat_provider(provider):
        return 0
    if not _hierarchy_titles_need_cloud_cleanup(chapters, book_title=book_title):
        logger.info("15j names pass skipped — all titles already clean (LLM call saved)")
        return 0

    client = LlmChatClient.from_config(temperature=0.1)
    compact = _compact_hierarchy_for_names(chapters)
    user = json.dumps({"book_title": book_title[:120], "chapters": compact}, ensure_ascii=False)
    raw = client.chat_with_provider(provider, system=_NAMES_SYSTEM, user=user, max_tokens=4096)
    parsed = _parse_names_json(raw or "")
    if not parsed:
        return 0
    return _apply_name_corrections(
        list(chapters),
        parsed,
        book_title=book_title,
        lines=lines,
        require_strict_heading_match=require_strict_heading_match,
    )


def run_hierarchy_openai_refinement(
    chapter_hierarchy: Dict[str, Any],
    *,
    lines: Optional[Sequence[Any]] = None,
    document_profile: Optional[Any] = None,
) -> Dict[str, Any]:
    """Stage 15j — OpenAI regroup (batched) + names + content-aware polish."""
    if not getattr(config, "HIERARCHY_OPENAI_ENABLED", True):
        return chapter_hierarchy

    if not hierarchy_needs_cloud_refinement(chapter_hierarchy):
        out = copy.deepcopy(chapter_hierarchy)
        meta = dict(out.get("meta") or {})
        meta["hierarchy_openai_method"] = "skipped_local_sufficient"
        meta["hierarchy_openai_skipped"] = True
        out["meta"] = meta
        logger.info("15j skipped — local hierarchy sufficient (regroup/names/polish not needed)")
        return out

    out = copy.deepcopy(chapter_hierarchy)
    chapters = list(out.get("chapters") or [])
    if not chapters:
        return out

    book_title = _norm(
        str(out.get("book_title") or (out.get("meta") or {}).get("book_title") or "")
    )
    sections = _flatten_sections(chapters)
    if not sections:
        return out

    meta = dict(out.get("meta") or {})
    regrouped = False
    merged = 0
    name_changes = 0

    assignments = None
    if _hierarchy_needs_regroup(chapters, section_count=len(sections)):
        assignments = _openai_regroup_assignments(
            sections,
            book_title=book_title,
            current_chapters=len(chapters),
        )
    else:
        logger.info("15j regroup skipped — chapter count and section distribution already healthy")
    coalesced = 0
    if assignments:
        coalesced = coalesce_regroup_assignments(list(assignments), sections)
        chapters = _rebuild_from_assignments(sections, assignments)
        regrouped = True
    else:
        logger.info("15j OpenAI regroup failed or skipped; keeping prior chapter groups")

    min_secs = int(getattr(config, "HIERARCHY_OPENAI_MIN_SECTIONS_PER_CHAPTER", 3) or 3)
    min_chars = int(getattr(config, "HIERARCHY_OPENAI_MIN_CHAPTER_CHARS", 400) or 400)
    chapters, merge_stats = consolidate_chapter_hierarchy(
        chapters,
        min_sections=min_secs,
        min_chars=min_chars,
    )
    merged = int(merge_stats.get("tiny_merged", 0)) + int(merge_stats.get("related_merged", 0))

    require_strict = bool(
        document_profile and getattr(document_profile, "require_strict_heading_match", False)
    )

    # Cheap local refinement first so the (gated) LLM names pass can be skipped
    # whenever deterministic fixes already produced clean titles.
    semantic_changes = _refine_semantic_titles(chapters, book_title=book_title)
    name_changes = _openai_name_corrections(
        chapters,
        book_title=book_title,
        lines=lines,
        require_strict_heading_match=require_strict,
    )
    polish_changes = _openai_polish_noisy_titles(
        chapters,
        book_title=book_title,
        lines=lines,
        require_strict_heading_match=require_strict,
    )
    name_changes += semantic_changes + polish_changes

    from src.modules.structure.final_structuring.heading_cleanup import (
        disambiguate_duplicate_chapter_titles,
        disambiguate_duplicate_section_headings,
        merge_duplicate_named_chapters,
        sanitize_merged_section_titles,
    )
    from src.modules.structure.final_structuring.subheading_refinement import (
        fix_unacceptable_section_titles,
        fix_verbose_section_titles,
    )

    chapters, duplicate_chapter_merges = merge_duplicate_named_chapters(chapters)
    sanitize_merged_section_titles(chapters)
    name_changes += fix_verbose_section_titles({"chapters": chapters})
    name_changes += disambiguate_duplicate_section_headings(chapters)
    name_changes += disambiguate_duplicate_chapter_titles(chapters)

    unacceptable_fixes = fix_unacceptable_section_titles(
        {"chapters": chapters},
        use_transformers=True,
        lines=lines,
        require_strict_heading_match=require_strict,
    )
    name_changes += unacceptable_fixes

    topic_count = sum(
        1 + len(s.get("subheadings") or []) for ch in chapters for s in ch.get("sections") or []
    )
    meta.update(
        {
            "hierarchy_openai_method": "openai_regroup+names" if regrouped else "openai_names_only",
            "hierarchy_openai_regrouped": regrouped,
            "hierarchy_openai_coalesced_starts": coalesced,
            "hierarchy_openai_merged_chapters": merged,
            "hierarchy_openai_tiny_merged": merge_stats.get("tiny_merged", 0),
            "hierarchy_openai_related_merged": merge_stats.get("related_merged", 0),
            "hierarchy_openai_name_changes": name_changes,
            "hierarchy_openai_semantic_titles": semantic_changes,
            "hierarchy_openai_polish_titles": polish_changes,
            "hierarchy_openai_duplicate_chapter_merges": duplicate_chapter_merges,
            "total_chapters": len(chapters),
            "total_sections": sum(len(c.get("sections") or []) for c in chapters),
            "total_topics": topic_count,
        }
    )
    out["chapters"] = chapters
    out, enforce_stats = enforce_chapter_structure(out)
    meta = dict(out.get("meta") or {})
    meta["hierarchy_enforce_stats"] = enforce_stats
    out["meta"] = meta
    logger.info(
        "15j hierarchy OpenAI: regrouped=%s merged=%s name_changes=%s chapters=%s",
        regrouped,
        merged,
        name_changes,
        len(out.get("chapters") or []),
    )
    return out

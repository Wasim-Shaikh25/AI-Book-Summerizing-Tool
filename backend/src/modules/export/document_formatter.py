"""Assemble markdown notes with cover page, TOC, and chapter page breaks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

# Pandoc OpenXML page break (works for DOCX export; harmless in plain MD viewers).
PAGE_BREAK = (
    "\n\n```{=openxml}\n"
    "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>\n"
    "```\n\n"
)


def resolve_export_missing_body_mode() -> str:
    """How export handles hierarchy sections with no rewrite body."""
    import os

    from src import config

    raw = (
        os.environ.get("EXPORT_MISSING_BODY_MODE")
        or getattr(config, "EXPORT_MISSING_BODY_MODE", "placeholder")
        or "placeholder"
    ).strip().lower()
    if raw in {"placeholder", "fail", "skip"}:
        return raw
    return "placeholder"


def _resolve_section_body(
    *,
    section_id: str,
    section: Dict[str, Any],
    rewritten: Dict[str, str],
    missing_body_mode: str,
) -> Optional[str]:
    body = rewritten.get(section_id, "").strip()
    if body:
        return body
    frag = section.get("fragment") or {}
    preview = str(frag.get("preview") or "").strip()
    if preview:
        return preview
    if missing_body_mode == "skip":
        return None
    if missing_body_mode == "fail":
        raise ValueError(f"No rewrite body available for section {section_id}")
    page = section.get("page_number") or "?"
    return (
        f"Source text not available for this section — refer to page {page} "
        "of the source document."
    )


def _section_id_tag(section_id: str) -> str:
    """Inline HTML-comment anchor (`<!-- sid:SXX -->`) appended to a section heading.

    Enables a deterministic section_id -> body join in export/audit regardless of
    how the display title was cleaned. Stripped before DOCX render
    (``note_body_docx.strip_section_id_tags``) and invisible in rendered markdown.
    """
    sid = (section_id or "").strip()
    return f" <!-- sid:{sid} -->" if sid else ""


@dataclass
class BookCoverMeta:
    title: str
    subtitle: str = "Study Notes"
    source_pdf: str = ""
    user_instruction: str = ""
    generated_at: str = ""
    chapter_count: int = 0
    section_count: int = 0
    topic_count: int = 0
    extra_lines: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.utcnow().strftime("%B %d, %Y")


@dataclass
class TocEntry:
    title: str
    page_start: Optional[int] = None
    chapter_id: str = ""


def build_cover_page(meta: BookCoverMeta) -> str:
    """First page: centered book title and metadata table."""
    title = (meta.title or "Untitled Book").strip()
    lines: List[str] = [
        '<div style="text-align: center;">',
        "",
        f"# {title}",
        "",
        f"### {meta.subtitle}",
        "",
        "</div>",
        "",
        "| | |",
        "|:---|:---|",
        f"| **Book** | {title} |",
    ]
    if meta.source_pdf:
        lines.append(f"| **Source PDF** | {meta.source_pdf} |")
    lines.append(f"| **Generated** | {meta.generated_at} |")
    if meta.chapter_count:
        lines.append(f"| **Chapters** | {meta.chapter_count} |")
    if meta.section_count:
        lines.append(f"| **Sections** | {meta.section_count} |")
    if meta.topic_count:
        lines.append(f"| **Topics** | {meta.topic_count} |")
    if meta.user_instruction:
        lines.append(f"| **Notes style** | {meta.user_instruction} |")
    for extra in meta.extra_lines:
        if extra.strip():
            lines.append(extra.strip())
    lines.append("")
    return "\n".join(lines)


def build_toc_section(entries: Sequence[TocEntry], hierarchy: Optional[Dict[str, Any]] = None) -> str:
    """Hierarchical table of contents — chapter then indented sections."""
    if not entries and not hierarchy:
        return ""
    from src.modules.structure.final_structuring.heading_title_engine import (
        resolve_chapter_display_heading,
        resolve_section_display_heading,
    )
    from src.shared.english_text import filter_english_heading

    chapters = list((hierarchy or {}).get("chapters") or [])
    if not chapters and entries:
        lines = ["# Table of Contents", ""]
        for i, entry in enumerate(entries, start=1):
            lines.append(f"## {i}. {entry.title.strip()}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    lines = ["# Table of Contents", ""]
    for i, ch in enumerate(chapters, start=1):
        title = resolve_chapter_display_heading(ch, use_transformers=False)
        title = filter_english_heading(title) or title
        if not title:
            continue
        lines.append(f"## {i}. {title}")
        for sec in ch.get("sections") or []:
            sec_h = resolve_section_display_heading(sec, chapter_heading=title, use_transformers=True)
            sec_h = filter_english_heading(sec_h) or sec_h
            if sec_h and len(sec_h) <= 120:
                lines.append(f"- {sec_h}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_chapter_block(heading: str, body: str, *, page_break_before: bool = True) -> str:
    """One chapter: optional page break + H1 heading + body."""
    parts: List[str] = []
    if page_break_before:
        parts.append(PAGE_BREAK.strip())
    parts.append(f"# {heading.strip()}")
    parts.append("")
    if body.strip():
        parts.append(body.strip())
    return "\n".join(parts)


def _strip_leading_page_break(text: str) -> str:
    marker = PAGE_BREAK.strip()
    if text.startswith(marker):
        return text[len(marker) :].lstrip()
    return text


def assemble_notes_document(
    *,
    cover: BookCoverMeta,
    toc_entries: Sequence[TocEntry],
    chapter_blocks: Sequence[str],
    hierarchy: Optional[Dict[str, Any]] = None,
    include_toc: bool = True,
) -> str:
    """
    Full document layout:
      1. Cover page (metadata)
      2. Page break
      3. Table of contents
      4. Page break
      5. Chapters (each starts on a new page)
    """
    parts: List[str] = [build_cover_page(cover).strip(), PAGE_BREAK.strip()]
    if include_toc and toc_entries:
        parts.append(build_toc_section(toc_entries, hierarchy=hierarchy).strip())
        parts.append(PAGE_BREAK.strip())
    first_chapter = True
    for block in chapter_blocks:
        text = block.strip()
        if not text:
            continue
        if first_chapter and include_toc and toc_entries:
            text = _strip_leading_page_break(text)
            first_chapter = False
        parts.append(text)
    from src.modules.generation.rewrite_validation import dedupe_consecutive_section_headings

    # Keep <!-- sid:SXX --> anchors in saved markdown for audit/sidecar joins.
    # DOCX render strips them via note_body_docx / markdown_docx_renderer.
    doc = "\n\n".join(parts).strip() + "\n"
    return dedupe_consecutive_section_headings(doc)


def toc_entries_from_hierarchy(hierarchy: Dict[str, Any]) -> List[TocEntry]:
    """All chapters from hierarchy for the TOC page (display-safe titles)."""
    from src.modules.structure.final_structuring.heading_title_engine import resolve_chapter_display_heading

    entries: List[TocEntry] = []
    for ch in hierarchy.get("chapters") or []:
        heading = resolve_chapter_display_heading(ch, use_transformers=False).strip()
        if not heading:
            continue
        entries.append(
            TocEntry(
                title=heading,
                page_start=ch.get("page_start"),
                chapter_id=str(ch.get("chapter_id") or ""),
            )
        )
    return entries


def chapter_blocks_from_hierarchy(
    hierarchy: Dict[str, Any],
    rewritten: Dict[str, str],
    *,
    bundle_size: int = 1,
    bundle_export: bool = False,
    chapter_page_breaks: Optional[bool] = None,
    user_instruction: str = "",
) -> tuple[List[str], List[TocEntry]]:
    """Build chapter markdown blocks from 15e + rewritten section map."""
    from src.modules.generation.rewrite_prompts import normalize_rewritten_section
    from src.modules.generation.rewrite_validation import normalize_heading, strip_redundant_section_heading
    from src.modules.generation.section_bundler import build_rewrite_bundles, resolve_chapter_page_breaks
    from src.modules.structure.final_structuring.chapter_placement import universal_clean_heading
    from src.modules.structure.final_structuring.heading_title_engine import (
        resolve_chapter_display_heading,
        resolve_section_display_heading,
    )
    from src.shared.english_text import filter_english_heading

    def _display_heading(
        heading: str,
        *,
        section: Optional[Dict[str, Any]] = None,
        subheadings: Optional[Sequence[Dict[str, Any]]] = None,
        page_number: Optional[int] = None,
        chapter_heading: str = "",
    ) -> str:
        from src.modules.quality.heuristics import classify_heading
        from src.modules.structure.dropped_heading_registry import partition_heading_to_study_title

        if section is not None:
            resolved = resolve_section_display_heading(
                section,
                chapter_heading=chapter_heading,
                use_transformers=True,
            )
            resolved = filter_english_heading(resolved) or resolved
        else:
            cleaned = universal_clean_heading(
                heading,
                subheadings=subheadings,
                page_number=page_number,
                use_transformers=False,
            )
            resolved = filter_english_heading(cleaned) or cleaned

        if classify_heading(resolved) != "looks_ok":
            parent = chapter_heading or str((section or {}).get("chapter_heading") or "")
            fallback = partition_heading_to_study_title(parent or resolved)
            if page_number is not None:
                fallback = f"{fallback} (p. {page_number})"
            resolved = filter_english_heading(fallback) or fallback
        from src.modules.structure.final_structuring.heading_title_engine import ensure_study_safe_heading

        return ensure_study_safe_heading(
            resolved,
            chapter_heading=chapter_heading,
            page_number=page_number,
        )

    def _append_subtopic_checklist(body: str, subheadings: Sequence[Dict[str, Any]]) -> str:
        """Optional export hint for missing subtopics — disabled by default (noisy in notes)."""
        from src.shared import config

        if not getattr(config, "EXPORT_APPEND_SUBTOPIC_CHECKLIST", False):
            return body
        if not body.strip() or not subheadings:
            return body
        body_norm = normalize_heading(body)
        missing: List[str] = []
        for sub in subheadings:
            label = _display_heading(str(sub.get("heading") or ""))
            if len(label) < 4 or is_weak_section_heading(label):
                continue
            if normalize_heading(label) not in body_norm:
                missing.append(label)
        if not missing:
            return body
        return body + "\n\n**Also cover:** " + "; ".join(missing[:8]) + "."

    from src.modules.generation.rewrite_validation import is_weak_section_heading

    use_bundles = bundle_export and bundle_size > 1
    if chapter_page_breaks is None:
        chapter_page_breaks = resolve_chapter_page_breaks(use_bundles=use_bundles)

    missing_body_mode = resolve_export_missing_body_mode()
    blocks: List[str] = []
    for ch in hierarchy.get("chapters") or []:
        ch_heading = resolve_chapter_display_heading(ch, use_transformers=False)
        ch_heading = filter_english_heading(ch_heading) or ch_heading
        if not ch_heading:
            continue
        sec_rows: List[Dict[str, Any]] = []
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            body = _resolve_section_body(
                section_id=sid,
                section=sec,
                rewritten=rewritten,
                missing_body_mode=missing_body_mode,
            )
            if body is None:
                continue
            sec_rows.append(
                {
                    "section_id": sid,
                    "heading": str(sec.get("heading") or "").strip(),
                    "chapter_heading": ch_heading,
                    "text": body,
                    "subheadings": list(sec.get("subheadings") or []),
                    "page_number": sec.get("page_number"),
                    "fragment": sec.get("fragment") or {},
                    "_section": sec,
                }
            )
        if not sec_rows:
            continue

        sec_parts: List[str] = []
        if bundle_export and bundle_size > 1:
            for bundle in build_rewrite_bundles(sec_rows, bundle_size=bundle_size):
                inner: List[str] = []
                for sid, heading in zip(bundle.section_ids, bundle.headings):
                    sec_row = next((r for r in sec_rows if str(r.get("section_id")) == sid), {})
                    body = strip_redundant_section_heading(
                        rewritten.get(sid, "").strip(),
                        heading,
                    )
                    if not body:
                        body = str(sec_row.get("text") or "").strip()
                    display = _display_heading(
                        heading,
                        section=sec_row.get("_section") or sec_row,
                        subheadings=sec_row.get("subheadings"),
                        page_number=sec_row.get("page_number"),
                        chapter_heading=ch_heading,
                    )
                    if not body:
                        continue
                    body = normalize_rewritten_section(body, user_instruction=user_instruction)
                    body = _append_subtopic_checklist(body, list(sec_row.get("subheadings") or []))
                    inner.append(f"### {display}{_section_id_tag(sid)}\n\n{body}")
                if inner:
                    sec_parts.append(f"## {bundle.label}\n\n" + "\n\n".join(inner))
        else:
            for row in sec_rows:
                sid = str(row.get("section_id") or "")
                heading = str(row.get("heading") or "").strip()
                body = strip_redundant_section_heading(
                    rewritten.get(sid, "").strip(),
                    heading,
                )
                if not body:
                    body = str(row.get("text") or "").strip()
                display = _display_heading(
                    heading,
                    section=row.get("_section") or row,
                    subheadings=row.get("subheadings"),
                    page_number=row.get("page_number"),
                    chapter_heading=ch_heading,
                )
                if body:
                    body = normalize_rewritten_section(body, user_instruction=user_instruction)
                    body = _append_subtopic_checklist(body, list(row.get("subheadings") or []))
                sec_parts.append(f"## {display}{_section_id_tag(sid)}\n\n{body}")

        if sec_parts:
            blocks.append(
                format_chapter_block(
                    ch_heading,
                    "\n\n".join(sec_parts),
                    page_break_before=chapter_page_breaks,
                )
            )
    return blocks, toc_entries_from_hierarchy(hierarchy)


def cover_from_hierarchy_meta(
    *,
    title: str,
    hierarchy: Optional[Dict[str, Any]] = None,
    source_pdf: str = "",
    user_instruction: str = "",
) -> BookCoverMeta:
    meta = hierarchy.get("meta") if hierarchy else {}
    chapter_count = len(hierarchy.get("chapters") or []) if hierarchy else 0
    if not chapter_count and meta:
        chapter_count = int(meta.get("total_chapters") or 0)
    from src.shared.notes_export_style import default_cover_subtitle

    return BookCoverMeta(
        title=title,
        subtitle=default_cover_subtitle(),
        source_pdf=source_pdf,
        user_instruction=user_instruction,
        chapter_count=chapter_count,
        section_count=int(meta.get("total_sections") or meta.get("processed_section_count") or 0) if meta else 0,
        topic_count=int(meta.get("total_topics") or 0) if meta else 0,
    )


def flat_chapter_blocks(rewritten_sections: Sequence[tuple[str, str]]) -> tuple[List[str], List[TocEntry]]:
    """Fallback when no 15e hierarchy: one pseudo-chapter per section with page breaks."""
    blocks: List[str] = []
    toc: List[TocEntry] = []
    for heading, body in rewritten_sections:
        if not body.strip():
            continue
        toc.append(TocEntry(title=heading))
        blocks.append(format_chapter_block(heading, body, page_break_before=True))
    return blocks, toc


def rebuild_notes_markdown(
    *,
    cover: BookCoverMeta,
    hierarchy: Dict[str, Any],
    rewritten: Dict[str, str],
    include_toc: bool = True,
    bundle_size: int = 1,
    bundle_export: bool = False,
    chapter_page_breaks: Optional[bool] = None,
) -> str:
    """Rebuild full notes markdown from hierarchy + section_id map (correct order + sid tags)."""
    import copy

    from src.modules.structure.final_structuring.hierarchy_export import refine_hierarchy_for_export

    hierarchy = refine_hierarchy_for_export(hierarchy)
    cover.chapter_count = len(hierarchy.get("chapters") or []) or cover.chapter_count
    chapter_blocks, toc_entries = chapter_blocks_from_hierarchy(
        hierarchy,
        rewritten,
        bundle_size=bundle_size,
        bundle_export=bundle_export,
        chapter_page_breaks=chapter_page_breaks,
        user_instruction=cover.user_instruction,
    )
    return assemble_notes_document(
        cover=cover,
        toc_entries=toc_entries,
        chapter_blocks=chapter_blocks,
        hierarchy=hierarchy,
        include_toc=include_toc,
    )

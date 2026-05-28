"""Assemble markdown notes with cover page, TOC, and chapter page breaks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

# Pandoc OpenXML page break (works for DOCX export; harmless in plain MD viewers).
PAGE_BREAK = (
    "\n\n```{=openxml}\n"
    "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>\n"
    "```\n\n"
)


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
    if not entries:
        return ""
    chapters = list((hierarchy or {}).get("chapters") or [])
    chap_by_title = {str(c.get("heading") or "").strip(): c for c in chapters}

    lines = ["# Table of Contents", ""]
    for i, entry in enumerate(entries, start=1):
        title = entry.title.strip()
        lines.append(f"## {i}. {title}")
        ch = chap_by_title.get(title) or {}
        for sec in ch.get("sections") or []:
            sec_h = str(sec.get("heading") or "").strip()
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
    return "\n\n".join(parts).strip() + "\n"


def toc_entries_from_hierarchy(hierarchy: Dict[str, Any]) -> List[TocEntry]:
    """All chapters from 15e for the TOC page."""
    entries: List[TocEntry] = []
    for ch in hierarchy.get("chapters") or []:
        heading = str(ch.get("heading") or "").strip()
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
) -> tuple[List[str], List[TocEntry]]:
    """Build chapter markdown blocks from 15e + rewritten section map."""
    blocks: List[str] = []
    for ch in hierarchy.get("chapters") or []:
        ch_heading = str(ch.get("heading") or "").strip()
        if not ch_heading:
            continue
        sec_parts: List[str] = []
        has_content = False
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            body = rewritten.get(sid, "").strip()
            if not body:
                continue
            has_content = True
            sec_heading = str(sec.get("heading") or "").strip()
            sec_parts.append(f"## {sec_heading}\n\n{body}")
        if not has_content:
            continue
        blocks.append(format_chapter_block(ch_heading, "\n\n".join(sec_parts), page_break_before=True))
    return blocks, toc_entries_from_hierarchy(hierarchy)


def cover_from_hierarchy_meta(
    *,
    title: str,
    hierarchy: Optional[Dict[str, Any]] = None,
    source_pdf: str = "",
    user_instruction: str = "",
) -> BookCoverMeta:
    meta = hierarchy.get("meta") if hierarchy else {}
    return BookCoverMeta(
        title=title,
        source_pdf=source_pdf,
        user_instruction=user_instruction,
        chapter_count=int(meta.get("total_chapters") or 0) if meta else 0,
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

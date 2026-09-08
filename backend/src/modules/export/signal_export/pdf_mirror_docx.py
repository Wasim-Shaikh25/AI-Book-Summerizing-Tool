"""PDF-mirror Markdown + DOCX exporter for the signal-sections pipeline.

Output Markdown structure (one document):

    <cover header band — added by docx_theme>
    # <Book Title>

    # Table of Contents

    | Chapter | Pages |
    |---|---|
    | C1. <chapter heading>   | 12-34 |
    ...

    # <Chapter heading>            (## in DOCX -> add_heading level=1)
    ## <Section heading>           (## in DOCX -> add_heading level=2)
    <rewritten body, may contain ### inner headings allowed by decider>

Chapter / section heading text comes straight from ``signal_hierarchy.json``
(no LLM renaming). When a section's rewrite failed, the exporter inserts a
``> [signal] rewrite unavailable — original source preserved`` callout
followed by the raw PDF source so the structure is never silently lost.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.modules.export.markdown_docx_renderer import export_markdown_file_to_docx

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _pages_label(page_start: Any, page_end: Any) -> str:
    if isinstance(page_start, int) and isinstance(page_end, int):
        return str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
    if isinstance(page_start, int):
        return str(page_start)
    if isinstance(page_end, int):
        return str(page_end)
    return ""


def _build_toc(chapters: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = [
        "# Table of Contents",
        "",
        "| Chapter | Pages |",
        "| --- | --- |",
    ]
    for ch in chapters:
        ch_id = str(ch.get("chapter_id") or "")
        ch_heading = _norm(str(ch.get("heading") or ""))
        pages = _pages_label(ch.get("page_start"), ch.get("page_end"))
        lines.append(f"| {ch_id}. {ch_heading} | {pages} |")
    lines.append("")
    return "\n".join(lines)


def _format_section_body(
    *,
    body_md: str,
    fallback_source: str,
) -> str:
    body = (body_md or "").strip()
    if body:
        return body
    raw = (fallback_source or "").strip()
    if not raw:
        return "> [signal] rewrite unavailable — no source text in this section."
    return (
        "> [signal] rewrite unavailable — original source preserved below.\n\n"
        + raw
    )


def assemble_signal_markdown(
    *,
    hierarchy: Dict[str, Any],
    rewritten_by_section_id: Dict[str, str],
    book_title: Optional[str] = None,
    include_toc: bool = True,
) -> str:
    """Build the final Markdown document mirroring the PDF hierarchy."""
    chapters = list(hierarchy.get("chapters") or [])
    title = _norm(book_title or str(hierarchy.get("book_title") or "") or "Study Notes")

    parts: List[str] = [
        '<div align="center">',
        f"# {title}",
        "</div>",
        "",
    ]

    if include_toc and chapters:
        parts.append(_build_toc(chapters))

    for ch in chapters:
        ch_heading = _norm(str(ch.get("heading") or ""))
        if not ch_heading:
            continue
        parts.append(f"# {ch_heading}")
        parts.append("")
        for sec in ch.get("sections") or []:
            sec_heading = _norm(str(sec.get("heading") or ""))
            if not sec_heading:
                continue
            parts.append(f"## {sec_heading}")
            parts.append("")
            section_id = str(sec.get("section_id") or "")
            body_md = rewritten_by_section_id.get(section_id, "")
            fallback = str(sec.get("body") or "")
            parts.append(_format_section_body(body_md=body_md, fallback_source=fallback))
            parts.append("")

    return "\n".join(parts).strip() + "\n"


def export_signal_docx(
    *,
    markdown_text: str,
    output_path: Path | str,
    theme: Optional[str] = None,
) -> str:
    """Render the signal Markdown to a DOCX using the project's standard renderer."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    return export_markdown_file_to_docx(
        markdown_text,
        out,
        reference_docx=None,
        theme=theme,
    )


def write_signal_markdown(*, markdown_text: str, output_path: Path | str) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown_text, encoding="utf-8")
    return str(out)

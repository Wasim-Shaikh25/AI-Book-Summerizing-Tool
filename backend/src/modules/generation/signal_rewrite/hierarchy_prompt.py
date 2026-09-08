"""Build the structural-aware prompt sent to Gemini Flash Lite for one section.

Key differences vs. the existing rewrite prompt:
* Full parent path is given (book -> chapter L1 -> section L2).
* Each inner heading is sent with its score + line position. The model is
  explicitly told to keep an inner heading as ``### ...`` only when it
  introduces real new content; otherwise fold it into prose.
* Previous + next L2 section heading text is sent (not just raw text) so the
  model knows what came before and what comes next.
* The L2 section title is NOT printed by the model (exporter prints it).

No subject names are referenced anywhere in the prompt.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


SIGNAL_REWRITE_SYSTEM_TEMPLATE = """You are rewriting one section from a study textbook.
Strictly use only the source text provided. Do not introduce facts, dates,
names, examples, or quotations that are not in the source.

UNIVERSAL OUTPUT RULES:
1. The exporter will print the section title above your output. Do NOT print it yourself.
2. Use ``### <inner heading>`` ONLY for inner headings that you decide are real
   new sub-topics with substantive content in the source. Fold anything that
   looks fragmentary, duplicate, or has no real new content into surrounding
   prose with no heading at all.
3. Write clear plain English paragraphs. Use bullet or numbered lists ONLY for
   genuine enumerations (steps, examples, named items).
4. Do not echo the section title as a bullet or as the first line.
5. Do not write meta filler ("This section covers...", "We will discuss...").
6. Do not output admin/syllabus blocks (course objectives, learning outcomes,
   module labels, reading lists, "Also cover:" checklists).
7. English only. Skip or paraphrase non-English source text in plain English.
8. Do not wrap your whole answer in a code fence.

USER STYLE REQUEST (apply on top of the rules above):
{user_instruction}
"""


_TAIL_BREAK_MIN = 40
_HEAD_BREAK_MIN = 40


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _truncate_tail(text: str, *, max_chars: int) -> str:
    t = (text or "").strip()
    if not t or max_chars <= 0:
        return ""
    if len(t) <= max_chars:
        return t
    chunk = t[-max_chars:]
    space = chunk.find(" ")
    if space > _TAIL_BREAK_MIN:
        chunk = chunk[space + 1 :]
    return chunk.strip()


def _truncate_head(text: str, *, max_chars: int) -> str:
    t = (text or "").strip()
    if not t or max_chars <= 0:
        return ""
    if len(t) <= max_chars:
        return t
    chunk = t[:max_chars]
    space = chunk.rfind(" ")
    if space > _HEAD_BREAK_MIN:
        chunk = chunk[:space]
    return chunk.strip()


def build_signal_system_prompt(*, user_instruction: str) -> str:
    """Return the system prompt with the user style instruction baked in."""
    instr = (user_instruction or "").strip() or "Rewrite the source into clear study notes."
    return SIGNAL_REWRITE_SYSTEM_TEMPLATE.format(user_instruction=instr)


def _format_inner_headings_block(inner_headings: Sequence[Dict[str, Any]]) -> str:
    """Render inner headings with score + line position for the LLM."""
    if not inner_headings:
        return "(none detected)"
    lines: List[str] = []
    for i, h in enumerate(inner_headings, start=1):
        text = _norm(str(h.get("text") or ""))
        if not text:
            continue
        line_id = h.get("line_id")
        page = h.get("page_number")
        confidence = h.get("confidence")
        signals = h.get("signals_used") or []
        bits: List[str] = []
        if isinstance(line_id, int):
            bits.append(f"line {line_id}")
        if isinstance(page, int):
            bits.append(f"page {page}")
        if isinstance(confidence, (int, float)):
            bits.append(f"confidence {float(confidence):.2f}")
        if signals:
            bits.append("signals: " + ", ".join(str(s) for s in signals[:3]))
        meta = " | ".join(bits) if bits else "no metadata"
        lines.append(f'{i}. "{text}"   ({meta})')
    return "\n".join(lines) if lines else "(none detected)"


def build_signal_section_prompt(
    *,
    book_title: str,
    chapter_number: int,
    chapter_heading: str,
    section_number: int,
    section_heading: str,
    section_page_start: Optional[int],
    section_page_end: Optional[int],
    source_text: str,
    inner_headings: Sequence[Dict[str, Any]],
    prev_section_heading: str = "",
    prev_section_tail: str = "",
    next_section_heading: str = "",
    next_section_head: str = "",
    overlap_chars: int = 600,
) -> str:
    """Build the per-section user prompt for the rewrite call."""
    section_pages = "?"
    if isinstance(section_page_start, int) and isinstance(section_page_end, int):
        if section_page_start == section_page_end:
            section_pages = str(section_page_start)
        else:
            section_pages = f"{section_page_start}-{section_page_end}"
    elif isinstance(section_page_start, int):
        section_pages = str(section_page_start)

    parts: List[str] = [
        "PARENT PATH (context only — do NOT repeat as headings):",
        f"  Book: {_norm(book_title) or '(untitled)'}",
        f"  Chapter L1 (#{chapter_number}): {_norm(chapter_heading) or '(untitled chapter)'}",
        "",
        "CURRENT SECTION (write the body for THIS and nothing else):",
        f"  Section number: {section_number}",
        f'  Section heading (L2, verbatim from PDF — DO NOT change or print):',
        f'    "{_norm(section_heading)}"',
        f"  Section page range: pages {section_pages}",
        "",
        "INNER HEADINGS detected in this section by the PDF parser:",
        "(These may be real sub-topics OR PDF noise. Decide per item:",
        "  * If it clearly introduces real new sub-content in the source text",
        "    below, render it as ``### <inner heading>`` followed by its prose.",
        "  * If it looks fragmentary, duplicate, partial, or has no real new",
        "    content, fold it into the surrounding prose with NO heading.",
        ")",
        _format_inner_headings_block(inner_headings),
        "",
    ]

    if prev_section_heading or prev_section_tail:
        tail = _truncate_tail(prev_section_tail, max_chars=overlap_chars)
        parts.extend(
            [
                "PREVIOUS SECTION (continuity only — do NOT rewrite or repeat its facts):",
                f'  L2 prev heading: "{_norm(prev_section_heading) or "(unknown)"}"',
                f"  Tail of prev body (last ~{overlap_chars} chars):",
                f"  {tail}" if tail else "  (none)",
                "",
            ]
        )
    if next_section_heading or next_section_head:
        head = _truncate_head(next_section_head, max_chars=max(0, overlap_chars // 2))
        parts.extend(
            [
                "NEXT SECTION (so you stop before its topic):",
                f'  L2 next heading: "{_norm(next_section_heading) or "(unknown)"}"',
                f"  Head of next body (first ~{max(0, overlap_chars // 2)} chars):",
                f"  {head}" if head else "  (none)",
                "",
            ]
        )

    parts.extend(
        [
            "PRIMARY SOURCE (rewrite ONLY this; nothing outside it):",
            "----- SOURCE BEGIN -----",
            source_text or "(empty)",
            "----- SOURCE END -----",
        ]
    )
    return "\n".join(parts)

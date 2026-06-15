"""Strict markdown cleanup for LLM rewrite output — unpack run-ons; bullets or paragraphs."""

from __future__ import annotations

import re
from typing import List, Optional

# NOTE: "Course Outcomes" is intentionally NOT a callout — it is dropped as
# syllabus noise by `_strip_syllabus_blocks` and `notes_body_postprocess`.
# Listing it here too would format-then-strip (an internal contradiction).
_CALLOUT_LABELS = (
    "Learning Objectives",
    "Key Points",
    "Quick Revision",
    "Definition",
    "Important",
    "Note",
    "Summary",
    "Exam Tip",
)

_CALLOUT_LINE_RE = re.compile(
    r"^\*{0,2}(" + "|".join(re.escape(l) for l in _CALLOUT_LABELS) + r")\*{0,2}\s*:?\s*(.*)$",
    re.I,
)

_SECTION_SUBHEADING_RE = re.compile(
    r"^(Section\s+\d+[A-Za-z]?(?:\s*\([^)]+\))?\s*:\s*.+)$",
    re.I,
)

_RUNON_BULLET_SPLIT_RE = re.compile(r"(?<=[.!?:])\s+-\s+")
_INLINE_NUMBERED_RE = re.compile(r"(?:^|\s)(\d+)\.\s+")
_ORDERED_LINE_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_BOLD_SPAN_RE = re.compile(r"\*\*([^*]+)\*\*:?")
_DASH_BOLD_SPLIT_RE = re.compile(r"\s+-\s+(?=\*\*)")
_SENTENCE_END_BOLD_RE = re.compile(r"(?<=[.!?])\s+(?=\*\*)")


def renumber_ordered_list_blocks(lines: List[str]) -> List[str]:
    """Restart ordered-list numbering at 1 for each separate list block.

    Fixes LLM output that continues ``6. 7. 8.`` in a new topic/section where
    a fresh list should start at ``1.``. A new block starts after any non-empty
    non-ordered line or a blank line.
    """
    out: List[str] = []
    block_indent: Optional[str] = None
    counter = 0

    for ln in lines:
        m = _ORDERED_LINE_RE.match(ln)
        if m:
            indent, body = m.group(1), m.group(3)
            if block_indent != indent:
                block_indent = indent
                counter = 0
            counter += 1
            out.append(f"{indent}{counter}. {body}")
            continue

        stripped = (ln or "").strip()
        if not stripped:
            block_indent = None
            counter = 0
        else:
            block_indent = None
            counter = 0
        out.append(ln)
    return out


def renumber_ordered_list_text(text: str) -> str:
    """Apply :func:`renumber_ordered_list_blocks` to a markdown fragment."""
    if not (text or "").strip():
        return text or ""
    return "\n".join(renumber_ordered_list_blocks(text.splitlines()))


def prefer_paragraph_format(user_instruction: str = "") -> bool:
    """True when export style or user instruction requests paragraph-first notes."""
    try:
        from src.shared.notes_export_style import is_book_export_style

        if is_book_export_style():
            return True
    except Exception:
        pass
    explicit = (user_instruction or "").strip()
    if not explicit:
        return False
    try:
        from src.modules.generation.rewrite_prompts import user_prefers_paragraphs

        return user_prefers_paragraphs(explicit)
    except Exception:
        return False


def _bold_spans(text: str) -> List[re.Match[str]]:
    return list(_BOLD_SPAN_RE.finditer(text or ""))


def _has_inline_bold_subheading(text: str) -> bool:
    """True when **Label** appears mid-line or multiple bold labels share one line."""
    t = (text or "").strip()
    if not t or t.startswith(("#", "-", "|", ">", "```")):
        return False
    matches = _bold_spans(t)
    if not matches:
        return False
    if len(matches) >= 2:
        return True
    m = matches[0]
    if m.start() > 0:
        return True
    return bool(t[m.end() :].strip())


def _needs_paragraph_unpack(text: str) -> bool:
    t = (text or "").strip()
    if not t or t.startswith(("#", "-", "|", ">", "```")):
        return False
    if _has_inline_bold_subheading(t):
        return True
    if _DASH_BOLD_SPLIT_RE.search(t):
        return True
    if t.count("**") >= 4 and " - " in t:
        return True
    if t.startswith("**") and t.count(" - ") >= 2:
        return True
    return False


def split_inline_bold_subheadings(line: str) -> List[str]:
    """
    Split 'prose. **Soundness of Mind** More prose. **Muslim Identity** More'
    into separate subheading + paragraph lines.
    """
    text = (line or "").strip()
    if not _has_inline_bold_subheading(text):
        return [line]

    matches = _bold_spans(text)
    lines: List[str] = []
    pos = 0

    for idx, match in enumerate(matches):
        if match.start() > pos:
            before = text[pos : match.start()].strip()
            if before:
                if lines and lines[-1].strip() and not lines[-1].startswith("**"):
                    lines.append("")
                lines.append(before)

        title = match.group(1).strip()
        content_start = match.end()
        content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip().lstrip("- ").strip()

        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"**{title}**")
        if content:
            lines.append(content)
        pos = content_end

    collapsed: List[str] = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                collapsed.append("")
            continue
        blank = 0
        collapsed.append(ln)
    return collapsed or [line]


def _emit_clauses(content: str, *, use_bullets: bool) -> List[str]:
    parts = re.split(r"\s+-\s+", (content or "").strip())
    out: List[str] = []
    for part in parts:
        p = part.strip().lstrip("- ").strip()
        if not p:
            continue
        out.append(f"- {p}" if use_bullets else p)
    return out


def unpack_runon_paragraph(line: str, *, use_bullets: bool = False) -> List[str]:
    """
    Unpack run-on prose with inline **subheadings** or ' - **Sub:**' chains.
    """
    text = (line or "").strip()
    if not _needs_paragraph_unpack(text):
        return [line]

    if _has_inline_bold_subheading(text) and not _DASH_BOLD_SPLIT_RE.search(text):
        return split_inline_bold_subheadings(text)

    chunks = _DASH_BOLD_SPLIT_RE.split(text)
    lines: List[str] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        bold_spans = list(_BOLD_SPAN_RE.finditer(chunk))
        if not bold_spans:
            lines.extend(_emit_clauses(chunk, use_bullets=use_bullets))
            continue

        first = bold_spans[0]
        preamble = chunk[: first.start()].strip().rstrip(" .")
        if preamble:
            lines.append(preamble if preamble.endswith(".") else f"{preamble}.")

        for idx, match in enumerate(bold_spans):
            title = match.group(1).strip()
            content_start = match.end()
            content_end = bold_spans[idx + 1].start() if idx + 1 < len(bold_spans) else len(chunk)
            content = chunk[content_start:content_end].strip().lstrip("- ").strip()

            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"**{title}**")
            if content:
                lines.extend(_emit_clauses(content, use_bullets=use_bullets))

    collapsed: List[str] = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                collapsed.append("")
            continue
        blank = 0
        collapsed.append(ln)
    return collapsed or [line]


def _split_numbered_items(body: str, *, use_bullets: bool = True) -> List[str]:
    """Turn '1. foo 2. bar' into separate lines."""
    chunks = re.split(r"(\d+)\.\s+", (body or "").strip())
    if len(chunks) < 3:
        text = (body or "").strip()
        if not text:
            return []
        return [f"- {text}"] if use_bullets else [text]
    out: List[str] = []
    for i in range(1, len(chunks), 2):
        if i + 1 >= len(chunks):
            break
        content = chunks[i + 1].strip()
        if content:
            out.append(f"- {content}" if use_bullets else f"{chunks[i]}. {content}")
    return out


def _expand_inline_numbered_in_bullet(line: str) -> List[str]:
    """
    Expand '- Topics: 1. a 2. b' into a parent bullet plus indented numbered sub-items.
    """
    stripped = line.strip()
    if not stripped.startswith("- "):
        return [line]

    body = stripped[2:].strip()
    matches = list(_INLINE_NUMBERED_RE.finditer(body))
    if len(matches) < 2:
        return [line]

    prefix_end = matches[0].start()
    prefix = body[:prefix_end].rstrip(" :")
    lines: List[str] = []
    if prefix:
        lines.append(f"- {prefix}:")

    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        item = body[start:end].strip()
        if item:
            lines.append(f"  {match.group(1)}. {item}")
    return lines or [line]


def split_runon_bullets(line: str) -> List[str]:
    """Split '- point A. - point B.' into separate markdown bullets."""
    stripped = line.strip()
    if not stripped.startswith("- "):
        return [line]
    body = stripped[2:]
    if " - " not in body:
        return [line]

    parts = _RUNON_BULLET_SPLIT_RE.split(body)
    if len(parts) <= 1:
        parts = re.split(r"\s+-\s+", body)

    bullets = [f"- {p.strip()}" for p in parts if p.strip()]
    return bullets or [line]


def _normalize_plain_line(line: str, *, use_bullets: bool) -> List[str]:
    """Handle label lines and paragraphs with inline numbered lists."""
    stripped = line.strip()

    if _has_inline_bold_subheading(stripped):
        return split_inline_bold_subheadings(stripped)

    if _needs_paragraph_unpack(stripped):
        return unpack_runon_paragraph(stripped, use_bullets=use_bullets)

    callout = _CALLOUT_LINE_RE.match(stripped)
    if callout:
        label = callout.group(1).strip().title()
        body = (callout.group(2) or "").strip()
        out: List[str] = [f"**{label}**"]
        if body:
            if len(_INLINE_NUMBERED_RE.findall(body)) >= 2:
                out.extend(_split_numbered_items(body, use_bullets=use_bullets))
            elif use_bullets:
                out.append(f"- {body}")
            else:
                out.append(body)
        return out

    if _SECTION_SUBHEADING_RE.match(stripped):
        return [f"### {stripped}"]

    if len(_INLINE_NUMBERED_RE.findall(stripped)) >= 2 and not stripped.startswith(("-", "#", "|", ">")):
        colon = stripped.find(":")
        if 0 < colon < 48:
            label = stripped[:colon].strip()
            body = stripped[colon + 1 :].strip()
            if label and body:
                return [f"**{label}**", *_split_numbered_items(body, use_bullets=use_bullets)]
        return _split_numbered_items(stripped, use_bullets=use_bullets)

    return [line]


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def _split_long_paragraph(line: str, *, max_chars: int = 320) -> List[str]:
    """Keep paragraphs intact — export handles wrapping; do not split into pseudo-bullets."""
    text = (line or "").strip()
    if not text:
        return [line]
    return [text]


_BOLD_LABEL_DASH_RE = re.compile(r"^\*\*(.+?)\s*(?:-\s*){1,3}\*\*$")


def _clean_bold_label_artifacts(line: str) -> str:
    """Fix '**Course Outcomes - -**' → '**Course Outcomes**'."""
    stripped = (line or "").strip()
    m = _BOLD_LABEL_DASH_RE.match(stripped)
    if m:
        return f"**{m.group(1).strip()}**"
    return line


def _is_prose_sentence(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "-", "|", ">", "```")):
        return False
    if re.match(r"^\d+\.\s+", stripped):
        return False
    if _is_standalone_bold_label(stripped):
        return False
    return bool(re.search(r"[a-zA-Z]", stripped))


def _bulletize_prose_after_bold_labels(lines: List[str], *, use_bullets: bool) -> List[str]:
    """Turn plain sentences after **Subtopic** into bullets (exam-note mode)."""
    if not use_bullets:
        return lines
    out: List[str] = []
    after_bold = False
    for ln in lines:
        stripped = ln.strip()
        cleaned = _clean_bold_label_artifacts(stripped)
        if _is_standalone_bold_label(cleaned):
            if out and out[-1].strip():
                out.append("")
            out.append(cleaned)
            after_bold = True
            continue
        if after_bold and _is_prose_sentence(cleaned):
            out.append(f"- {cleaned.lstrip('- ').strip()}")
            continue
        after_bold = False
        out.append(ln)
    return out


def _attach_continuation_numbered_lists(lines: List[str]) -> List[str]:
    """
    Merge lines like:
      - Topics:
      1. First item.
      2. Second item.
    """
    out: List[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        out.append(ln)
        if stripped.startswith("- ") and stripped.rstrip().endswith(":"):
            j = i + 1
            numbered: List[str] = []
            while j < len(lines):
                nxt = lines[j].strip()
                if re.match(r"^\d+\.\s+", nxt):
                    numbered.append(nxt)
                    j += 1
                    continue
                if not nxt:
                    j += 1
                    break
                break
            if len(numbered) >= 2:
                out.extend([f"  {n}" if not n.startswith("  ") else n for n in numbered])
                i = j
                continue
        i += 1
    return out


def _is_standalone_bold_label(line: str) -> bool:
    stripped = (line or "").strip()
    return bool(
        stripped.startswith("**")
        and stripped.endswith("**")
        and stripped.count("**") == 2
    )


def _repair_split_bold_labels(lines: List[str]) -> List[str]:
    """
    Merge broken labels split across lines:
      **Definition**
      of a guardian**
    """
    out: List[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if (
            stripped.startswith("**")
            and stripped.endswith("**")
            and stripped.count("**") == 2
            and i + 1 < len(lines)
        ):
            nxt = lines[i + 1].strip()
            if nxt.endswith("**") and not nxt.startswith("**") and " " in nxt:
                title = f"{stripped[2:-2].strip()} {nxt[:-2].strip()}".strip()
                out.append(f"**{title}**")
                i += 2
                continue
        out.append(ln)
        i += 1
    return out


def _ensure_blank_before_subheadings(lines: List[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        stripped = ln.strip()
        if _is_standalone_bold_label(stripped):
            if out and out[-1].strip():
                out.append("")
        out.append(ln)
    return out


_ALSO_COVER_RE = re.compile(
    r"^\*{0,2}also cover\*{0,2}\s*:?\s*.*$",
    re.I,
)
_SYLLABUS_HEADING_RE = re.compile(
    r"^\*{0,2}(course\s+objectives?|course\s+outcomes?|learning\s+outcomes?|syllabus|reading\s+list)\*{0,2}\s*:?\s*$",
    re.I,
)
_MODULE_UNIT_LINE_RE = re.compile(r"^\*{0,2}(module|unit)\s+\d+\*{0,2}\s*:?\s*.*$", re.I)


def _strip_syllabus_blocks(lines: List[str]) -> List[str]:
    """Drop syllabus/admin heading blocks and their bullet lists from rewritten notes."""
    out: List[str] = []
    skip_block = False
    for ln in lines:
        stripped = (ln or "").strip()
        if _SYLLABUS_HEADING_RE.match(stripped) or _MODULE_UNIT_LINE_RE.match(stripped):
            skip_block = True
            continue
        if skip_block:
            if not stripped:
                continue
            if stripped.startswith(("-", "*", "•")) or re.match(r"^\d+\.\s+", stripped):
                continue
            if _is_standalone_bold_label(stripped):
                skip_block = False
            else:
                continue
        out.append(ln)
    return out


def _strip_also_cover_lines(lines: List[str]) -> List[str]:
    """Remove export-time 'Also cover:' checklist lines from note bodies."""
    out: List[str] = []
    for ln in lines:
        if _ALSO_COVER_RE.match((ln or "").strip()):
            continue
        out.append(ln)
    return out


def strict_normalize_markdown(text: str, *, user_instruction: str = "") -> str:
    """Enforce structured lines; paragraph mode when user requested minimal bullets."""
    if not (text or "").strip():
        return text or ""

    use_bullets = not prefer_paragraph_format(user_instruction)
    paragraph_mode = not use_bullets
    out_lines: List[str] = []
    in_fence = False

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue

        if not stripped:
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue

        if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith(">"):
            out_lines.append(line)
            continue

        if stripped.startswith("- "):
            for bullet in split_runon_bullets(_clean_bold_label_artifacts(stripped)):
                for expanded in _expand_inline_numbered_in_bullet(bullet):
                    out_lines.append(expanded)
            continue

        ordered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ordered:
            out_lines.append(line)
            continue

        expanded = _normalize_plain_line(line, use_bullets=use_bullets)
        if paragraph_mode:
            for part in expanded:
                out_lines.extend(_split_long_paragraph(part))
        else:
            out_lines.extend(expanded)

    out_lines = [_clean_bold_label_artifacts(ln) for ln in out_lines]
    out_lines = _strip_syllabus_blocks(out_lines)
    out_lines = _strip_also_cover_lines(out_lines)
    out_lines = _repair_split_bold_labels(out_lines)
    out_lines = _ensure_blank_before_subheadings(out_lines)
    out_lines = _bulletize_prose_after_bold_labels(out_lines, use_bullets=use_bullets)
    out_lines = _attach_continuation_numbered_lists(out_lines)
    out_lines = renumber_ordered_list_blocks(out_lines)

    # Collapse 3+ blank lines
    collapsed: List[str] = []
    blank_run = 0
    for ln in out_lines:
        if not ln.strip():
            blank_run += 1
            if blank_run <= 1:
                collapsed.append("")
            continue
        blank_run = 0
        collapsed.append(ln)

    return "\n".join(collapsed).strip()

"""Deterministic post-processing for rewritten section bodies."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

from src.modules.quality.heuristics import detect_outline_noise_in_body, norm

_STANDALONE_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*$")
_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+")
_META_FILLER_RE = re.compile(
    r"^(this (chapter|section|topic|unit|module)|in this (chapter|section|unit)|"
    r"we (will |shall )?(discuss|cover|learn|explore|examine|study)|"
    r"the (following|above) (section|chapter|points?|topics?)|"
    r"as (discussed|mentioned|noted) (above|earlier|below)|"
    r"it is important to note|this (note|section|chapter) (covers|explains|deals with|discusses)|"
    r"let us (discuss|explore|examine)|the purpose of this (section|chapter))\b",
    re.I,
)
_TEMPLATE_RE = re.compile(
    r"^(key points|quick revision|also cover|exam tip|summary|definition)\s*:?\s*$",
    re.I,
)
_INSTRUCTIONAL_HOURS_RE = re.compile(r"^instructional\s+hours?\s*:?\s*", re.I)


def _heading_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _should_drop_line(
    stripped: str,
    *,
    heading: str,
    chapter_heading: str,
) -> bool:
    if not stripped:
        return True
    if stripped.startswith("```"):
        return False
    if _HEADING_LINE_RE.match(stripped):
        return True
    if _META_FILLER_RE.search(stripped):
        return True
    if _TEMPLATE_RE.match(stripped):
        return True
    if _INSTRUCTIONAL_HOURS_RE.match(stripped):
        return True
    if detect_outline_noise_in_body(stripped):
        return True
    if _STANDALONE_BOLD_RE.match(stripped):
        return True
    for ref in (heading, chapter_heading):
        if ref and _heading_sim(ref, stripped) >= 0.88:
            return True
        bare = _STANDALONE_BOLD_RE.match(stripped)
        if bare and ref and _heading_sim(ref, bare.group(1)) >= 0.88:
            return True
    return False


def _clean_bullet_content(body: str) -> str:
    body = (body or "").strip()
    if not body:
        return ""
    if _should_drop_line(body, heading="", chapter_heading=""):
        return ""
    words = body.split()
    if len(words) < 3 and not body.endswith((".", "!", "?", ":")):
        return ""
    return body


def _has_real_content(text: str) -> bool:
    """True if text contains enough letters to be worth preserving."""
    return len(re.sub(r"[^A-Za-z]", "", text or "")) >= 12


def postprocess_rewritten_section(
    text: str,
    *,
    heading: str = "",
    chapter_heading: str = "",
) -> str:
    """Remove meta filler, heading echoes, outline lines, and thin junk from rewrite output."""
    raw = (text or "").strip()
    if not raw:
        return raw

    out_lines: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if out_lines and out_lines[-1].strip():
                out_lines.append("")
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            cleaned = _clean_bullet_content(bullet.group(2) or "")
            if cleaned:
                indent = bullet.group(1) or ""
                out_lines.append(f"{indent}- {cleaned}")
            continue

        if _should_drop_line(stripped, heading=heading, chapter_heading=chapter_heading):
            continue
        out_lines.append(line.rstrip())

    collapsed: List[str] = []
    for line in out_lines:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)

    result = "\n".join(collapsed).strip()
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")

    from src.modules.generation.markdown_format_normalizer import renumber_ordered_list_text

    result = renumber_ordered_list_text(result)

    # Robustness guard: aggressive filtering must never destroy a section that
    # carried real content. Fall back to a minimal clean (only heading/sid/meta
    # lines removed) so bodies are preserved rather than silently emptied.
    if not result and _has_real_content(raw):
        minimal: List[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _HEADING_LINE_RE.match(stripped) or _META_FILLER_RE.search(stripped):
                continue
            minimal.append(line.rstrip())
        fallback = "\n".join(minimal).strip()
        return fallback or raw
    return result

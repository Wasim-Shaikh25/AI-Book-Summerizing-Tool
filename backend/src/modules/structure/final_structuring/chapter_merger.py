"""Merge undersized chapters so TOC/body are not fragmented."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_MODULE_UNIT_RE = re.compile(r"^\s*(module|unit|part)\s+\d+", re.I)
_CHAPTER_NUM_RE = re.compile(r"^\s*chapter\s+\d+", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _is_hard_break_heading(text: str) -> bool:
    """MODULE/UNIT/PART/CHAPTER N — always keep as chapter boundary."""
    t = _norm(text)
    if not t:
        return False
    if _MODULE_UNIT_RE.match(t) or _CHAPTER_NUM_RE.match(t):
        return True
    return False


def _section_count(chapter: Dict[str, Any]) -> int:
    return len(chapter.get("sections") or [])


def _chapter_chars(chapter: Dict[str, Any]) -> int:
    total = 0
    for sec in chapter.get("sections") or []:
        frag = sec.get("fragment") or {}
        total += int(frag.get("chars") or 0)
        for sub in sec.get("subheadings") or []:
            sfrag = sub.get("fragment") or {}
            total += int(sfrag.get("chars") or 0)
    return total


def _is_module_page_partition(ch: Dict[str, Any]) -> bool:
    return (
        str(ch.get("assignment_method") or "") == "15h_module_page_split"
        or bool(ch.get("module_page_partition"))
    )


def _merge_chapter_into(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    target["sections"] = list(target.get("sections") or []) + list(source.get("sections") or [])
    if source.get("page_end") is not None:
        target["page_end"] = source.get("page_end")


def merge_undersized_chapters(
    chapters: List[Dict[str, Any]],
    *,
    min_sections: int = 2,
    min_chars: int = 400,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Merge consecutive tiny chapters into neighbors.
    Hard breaks (MODULE/UNIT/PART) are never merged away.
    """
    if not chapters or min_sections <= 1:
        return chapters, 0

    merged_count = 0
    out: List[Dict[str, Any]] = []

    for ch in chapters:
        title = _norm(str(ch.get("heading") or ""))
        secs = _section_count(ch)
        chars = _chapter_chars(ch)
        is_tiny = secs < min_sections or (secs < min_sections + 1 and chars < min_chars)
        is_hard = _is_hard_break_heading(title)

        if (
            is_tiny
            and not is_hard
            and out
            and not _is_hard_break_heading(_norm(str(out[-1].get("heading") or "")))
            and not _is_module_page_partition(ch)
            and not _is_module_page_partition(out[-1])
        ):
            _merge_chapter_into(out[-1], ch)
            merged_count += 1
            continue

        out.append(dict(ch))

    # Second pass: merge trailing singleton into previous
    if len(out) >= 2:
        last = out[-1]
        if (
            _section_count(last) < min_sections
            and not _is_hard_break_heading(_norm(str(last.get("heading") or "")))
            and not _is_module_page_partition(last)
            and not _is_module_page_partition(out[-2])
        ):
            prev = out[-2]
            if not _is_hard_break_heading(_norm(str(prev.get("heading") or ""))):
                _merge_chapter_into(prev, last)
                out.pop()
                merged_count += 1

    for i, ch in enumerate(out, start=1):
        ch["chapter_id"] = f"C{i}"
        sections = list(ch.get("sections") or [])
        if sections:
            ch["page_start"] = sections[0].get("page_number")
            ch["page_end"] = sections[-1].get("page_number")

    return out, merged_count

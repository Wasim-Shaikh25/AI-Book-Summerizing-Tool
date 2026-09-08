"""Build deduplicated, budgeted Q&A context with citation labels."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

_WS = re.compile(r"\s+")


def _norm_key(sec: Dict[str, Any]) -> str:
    sid = str(sec.get("section_id") or "").strip()
    if sid:
        return f"id:{sid}"
    heading = _WS.sub(" ", str(sec.get("heading") or "").strip().lower())
    page = sec.get("page_number")
    return f"h:{heading}:p:{page}"


def dedupe_sections(sections: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop duplicate sections by section_id or heading+page."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for sec in sections:
        key = _norm_key(sec)
        if key in seen:
            continue
        seen.add(key)
        out.append(sec)
    return out


def build_qa_context(
    sections: Sequence[Dict[str, Any]],
    *,
    max_chars: int = 12000,
    max_section_chars: int = 3000,
    include_citations: bool = True,
) -> Tuple[str, List[str]]:
    """
    Build LLM context string and source citation list from retrieved sections.

    Returns:
        (context_text, citation_labels)
    """
    unique = dedupe_sections(sections)
    parts: List[str] = []
    citations: List[str] = []
    used = 0

    for i, sec in enumerate(unique, start=1):
        heading = str(sec.get("heading") or "Section").strip()
        chapter = str(sec.get("chapter_heading") or "").strip()
        body = str(sec.get("text") or "").strip()
        if not body:
            continue

        label = heading
        if chapter and chapter.lower() not in heading.lower():
            label = f"{chapter} — {heading}"
        page = sec.get("page_number")
        if page is not None:
            label = f"{label} (p. {page})"

        cite_tag = f"[{i}]"
        citations.append(label)

        if include_citations:
            header = f"### {cite_tag} {heading}"
        else:
            header = f"### {heading}"

        if chapter and chapter.lower() not in heading.lower():
            header += f"\n*Chapter: {chapter}*"

        block = f"{header}\n{body[:max_section_chars]}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining < 200:
                break
            block = block[:remaining]
        parts.append(block)
        used += len(block)
        if used >= max_chars:
            break

    return "\n\n".join(parts), citations

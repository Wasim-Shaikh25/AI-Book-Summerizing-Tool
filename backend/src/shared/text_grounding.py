"""Subject-agnostic text-grounding signals.

Shared primitives for detecting index/contents-style text — enumerated title
lists (e.g. a contents page: ``65. Punishment for rape``) that give a rewrite
nothing to ground on. Used by:

- `generation/rewrite_fidelity.py`   — flag low-grounding source at rewrite time
- `structure/.../book_assembler.py`  — partition grounding gate (drop index bodies)
- `structure/contents_region.py`     — document-wide contents-page detection

All checks are measured (enumeration ratio + alphabetic character count) and
carry no subject vocabulary.
"""

from __future__ import annotations

import re
from typing import Sequence, Tuple

# A line that is only an enumerated label/title: "12. Title", "12) Title",
# "(12) Title", "12: Title". Anchored, requires at least one non-space char
# after the separator so blank enumerations do not match.
ENUM_TITLE_LINE_RE = re.compile(r"^\s*\(?\d{1,4}\)?\s*[.\):-]\s+\S")


def is_enumerated_title_line(line: str) -> bool:
    """True when a single line is just an enumerated title (index/contents row)."""
    return bool(ENUM_TITLE_LINE_RE.match((line or "").strip()))


def real_content_chars(text: str) -> int:
    """Count alphabetic characters, excluding enumerated title-list lines."""
    total = 0
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or ENUM_TITLE_LINE_RE.match(stripped):
            continue
        total += sum(1 for ch in stripped if ch.isalpha())
    return total


def enumerated_line_ratio(lines: Sequence[str]) -> Tuple[int, int]:
    """Return (enumerated_line_count, non_empty_line_count) for a group of lines."""
    non_empty = [ln for ln in (lines or []) if (ln or "").strip()]
    enum = sum(1 for ln in non_empty if ENUM_TITLE_LINE_RE.match(ln.strip()))
    return enum, len(non_empty)


def is_low_grounding(
    text: str,
    *,
    min_chars: int,
    enum_ratio: float = 0.6,
    min_lines: int = 3,
) -> bool:
    """True when text is an index/contents-style list OR has too little real prose.

    Used at rewrite time: such a source gives the model nothing to ground on, so
    it expands from prior knowledge. `min_chars` is the minimum real (non-list)
    character count for the text to count as a prose section.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return True
    if len(lines) >= min_lines:
        enum = sum(1 for ln in lines if ENUM_TITLE_LINE_RE.match(ln))
        if enum / len(lines) >= enum_ratio:
            return True
    return real_content_chars(text) < max(0, int(min_chars))


def is_contents_listing(
    text: str,
    *,
    enum_ratio: float = 0.6,
    min_lines: int = 3,
    min_real_chars: int = 40,
) -> bool:
    """Stricter check for the partition gate: drop only clear contents/index bodies.

    Unlike `is_low_grounding`, the prose floor here is low (`min_real_chars`, ~40)
    so genuinely short real sections are kept — only enumeration-dominated bodies
    (or bodies with almost no prose at all) are treated as index listings.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return True
    if len(lines) >= min_lines:
        enum = sum(1 for ln in lines if ENUM_TITLE_LINE_RE.match(ln))
        if enum / len(lines) >= enum_ratio:
            return True
    return real_content_chars(text) < max(0, int(min_real_chars))

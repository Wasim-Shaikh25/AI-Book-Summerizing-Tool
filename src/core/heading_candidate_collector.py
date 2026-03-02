from __future__ import annotations

import re
from typing import List, Sequence

from .models import HeadingCandidate, NormalizedLine


_NUMERIC_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s*[\)\.\-:]?\s+\S.+$")
_ROMAN_RE = re.compile(
    r"^\s*(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})"
    r"(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\s*[\)\.\-:]?\s+\S.+$",
    re.IGNORECASE,
)
_ALL_CAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s\-\&\(\)\/]*[A-Z0-9]$")


def _is_blank(s: str) -> bool:
    return not s or s.strip() == ""


def _is_title_case_line(s: str) -> bool:
    """
    Heuristic: most words start with uppercase and the rest lowercase.
    Intended to be permissive (not strict English title case).
    """
    s = s.strip()
    if not s:
        return False
    words = [w for w in re.split(r"\s+", s) if w]
    if len(words) == 0:
        return False
    # Avoid catching numeric headings here (handled separately)
    if _NUMERIC_RE.match(s) or _ROMAN_RE.match(s):
        return False

    scored = 0
    for w in words:
        # Strip punctuation around words
        core = re.sub(r"^[^\w]+|[^\w]+$", "", w)
        if not core:
            continue
        if core.isupper():
            # acronyms shouldn't disqualify
            scored += 1
        elif core[0].isupper():
            scored += 1
    return scored >= max(1, int(0.6 * len(words)))


def _looks_like_declaration(s: str) -> bool:
    """
    Declaration-style headings: short, few words, not ending with period,
    typically used like 'Definitions', 'Scope of Act', 'Legal Injury'.
    """
    s = s.strip()
    if not s or len(s) >= 120:
        return False
    if s.endswith("."):
        return False
    if _NUMERIC_RE.match(s) or _ROMAN_RE.match(s):
        return True
    # Avoid overly long multi-sentence lines
    if s.count(".") >= 2:
        return False

    # 1-6 words, primarily alphabetic
    words = [w for w in re.split(r"\s+", s) if w]
    if not (1 <= len(words) <= 6):
        return False

    # Allow Title Case or ALL CAPS or single-word nouns.
    if _is_title_case_line(s):
        return True
    if _ALL_CAPS_RE.match(s) and len(words) <= 8:
        return True
    if len(words) == 1 and re.match(r"^[A-Za-z][A-Za-z\-\&\/]*$", words[0]):
        return True

    return False


def _context(lines: Sequence[str], idx: int) -> tuple[List[str], List[str], str]:
    before = [
        lines[i] if 0 <= i < len(lines) else "" for i in (idx - 3, idx - 2, idx - 1)
    ]
    after = [
        lines[i] if 0 <= i < len(lines) else "" for i in (idx + 1, idx + 2, idx + 3)
    ]
    detected = lines[idx] if 0 <= idx < len(lines) else ""
    preview = "\n".join(
        [
            before[0],
            before[1],
            before[2],
            "",
            f"DETECTED_HEADING: {detected.strip()}",
            "",
            after[0],
            after[1],
            after[2],
        ]
    )
    return before, after, preview


def collect_heading_candidates(
    normalized: Sequence[NormalizedLine] | Sequence[str],
) -> List[HeadingCandidate]:
    """
    Universal, permissive heading candidate detector.

    Input may be:
    - Sequence[NormalizedLine] (preferred, per pipeline models)
    - Sequence[str] (allowed as a convenience during transition)

    Returns:
        List[HeadingCandidate] with full_context_preview containing the required
        DETECTED_HEADING marker.
    """
    # Normalize to list[str]
    if len(normalized) == 0:
        return []

    if isinstance(normalized[0], NormalizedLine):  # type: ignore[index]
        lines = [ln.text for ln in normalized]  # type: ignore[union-attr]
    else:
        lines = [str(x) for x in normalized]  # type: ignore[assignment]

    candidates: List[HeadingCandidate] = []
    seen_keys: set[tuple[int, str]] = set()

    for i, raw in enumerate(lines):
        text = (raw or "").rstrip("\n")
        stripped = text.strip()

        if _is_blank(stripped):
            continue

        # Basic permissive constraints
        if len(stripped) > 120:
            # Still allow numeric/roman headings even if slightly longer in rare cases
            if not (_NUMERIC_RE.match(stripped) or _ROMAN_RE.match(stripped)):
                continue

        prev_blank = _is_blank(lines[i - 1].strip()) if i - 1 >= 0 else True
        next_blank = _is_blank(lines[i + 1].strip()) if i + 1 < len(lines) else True

        # "Surrounded by empty lines" is a strong signal for short headings
        surrounded_by_blanks = prev_blank and next_blank

        # "Followed by a line break" interpreted as: next line exists and is not a continuation
        # (permissive: treat as signal when the next line is blank OR the current line ends cleanly)
        followed_by_break_signal = next_blank or stripped.endswith(":") or stripped.endswith(
            "-"
        )

        is_numeric = bool(_NUMERIC_RE.match(stripped))
        is_roman = bool(_ROMAN_RE.match(stripped))
        is_all_caps_short = bool(_ALL_CAPS_RE.match(stripped)) and len(stripped) <= 80
        is_title_case_short = _is_title_case_line(stripped) and len(stripped) <= 80

        # Permissive declaration-style
        is_declaration = _looks_like_declaration(stripped)

        # Candidate decision (collect generously)
        is_candidate = (
            is_numeric
            or is_roman
            or is_all_caps_short
            or (is_title_case_short and surrounded_by_blanks)
            or (len(stripped) <= 120 and (surrounded_by_blanks or followed_by_break_signal))
            or is_declaration
        )

        if not is_candidate:
            continue

        before_ctx, after_ctx, preview = _context(lines, i)

        # Stable-ish id: line index + normalized text
        compact = re.sub(r"\s+", " ", stripped)
        cid = f"L{i}:{compact[:60]}"

        key = (i, stripped)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        candidates.append(
            HeadingCandidate(
                id=cid,
                text=stripped,
                start_line=i,
                end_line=i,
                before_context=[b for b in before_ctx],
                after_context=[a for a in after_ctx],
                full_context_preview=preview,
                is_valid=None,
            )
        )

    return candidates

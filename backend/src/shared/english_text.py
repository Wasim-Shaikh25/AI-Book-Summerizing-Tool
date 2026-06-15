"""English-only text policy — discard or strip non-Latin script from pipeline text."""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional

# Latin letters (basic + extended) and common punctuation kept in output.
_ALLOWED_PUNCT = set(".,;:!?-'\"()/[]%&@#+–—…_*")


def english_only_enabled() -> bool:
    raw = os.environ.get("ENGLISH_ONLY", "").strip().lower()
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    try:
        from src import config as cfg

        return bool(getattr(cfg, "ENGLISH_ONLY", True))
    except Exception:
        return True


def _is_latin_letter(ch: str) -> bool:
    if not ch.isalpha():
        return False
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return ord(ch) < 128


def contains_english_letters(text: str) -> bool:
    """True when text has at least one Latin-script letter."""
    return any(_is_latin_letter(c) for c in text if c.isalpha())


def latin_letter_ratio(text: str) -> float:
    """Share of alphabetic characters that are Latin script (1.0 if no letters)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    latin = sum(1 for c in letters if _is_latin_letter(c))
    return latin / len(letters)


def is_primarily_english(text: str, *, min_latin_ratio: float = 0.85) -> bool:
    """False when the line/title is mostly non-English script."""
    if not english_only_enabled():
        return True
    t = (text or "").strip()
    if not t:
        return True
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return True
    return latin_letter_ratio(t) >= min_latin_ratio


def strip_to_english(text: str) -> str:
    """Remove non-Latin letters; keep digits, whitespace, and common punctuation."""
    if not text:
        return ""
    if not english_only_enabled():
        return text
    parts: list[str] = []
    for ch in text:
        if ch.isalpha():
            if _is_latin_letter(ch):
                parts.append(ch)
        elif ch.isdigit() or ch.isspace() or ch in _ALLOWED_PUNCT:
            parts.append(ch)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def filter_english_line(text: str) -> str:
    """
    English-only line filter for ingestion / fragments.
    - Strips non-Latin characters from mixed lines.
    - Returns empty string when the line is entirely non-English.
    """
    if not english_only_enabled():
        return text or ""
    stripped = strip_to_english(text or "")
    if not stripped:
        return ""
    if not contains_english_letters(stripped):
        return ""
    if not is_primarily_english(stripped):
        return ""
    return stripped


def filter_english_heading(title: str) -> Optional[str]:
    """
    Return cleaned English heading, or None if the title should be dropped.
    """
    if not english_only_enabled():
        t = re.sub(r"\s+", " ", (title or "").strip())
        return t or None
    cleaned = strip_to_english(title or "")
    if not cleaned or len(cleaned) < 2:
        return None
    if not contains_english_letters(cleaned):
        return None
    if not is_primarily_english(cleaned):
        return None
    return cleaned


def filter_english_body(text: str) -> str:
    """Filter multi-line body text line-by-line; drop non-English lines."""
    if not english_only_enabled():
        return text or ""
    kept: list[str] = []
    for line in (text or "").splitlines():
        filtered = filter_english_line(line)
        if filtered:
            kept.append(filtered)
    return "\n".join(kept).strip()


def english_only_rewrite_instruction() -> str:
    if not english_only_enabled():
        return ""
    return (
        "Output English only. Do not include Hindi, Urdu, Arabic, or other non-English script. "
        "If the source has non-English text, skip it or explain the idea in simple English."
    )

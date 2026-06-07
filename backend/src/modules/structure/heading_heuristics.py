"""
Deterministic heading heuristics (no LLM).

Extracted from the former heading_validation module for tests and reuse.
"""

from __future__ import annotations

import re

_ENUM_LIST_ITEM_RE = re.compile(r"^\s*\d+\.\s+\S+")
_SECTION_NUMBER_RE = re.compile(r"^\s*\d+\.\d+\s+\S+")


def should_force_invalid_enumerated_list_item(text: str) -> bool:
    """
    Treat single-level enumerated items like "3. Deterrence: ..." as body-list items, not TOC headings.
    Do not block true section headings like "1.2 Something ..." (dot-digit).
    """
    t = (text or "").strip()
    if not t:
        return False
    if _SECTION_NUMBER_RE.match(t):
        return False
    if _ENUM_LIST_ITEM_RE.match(t):
        if len(t) >= 55:
            return True
        if ":" in t and len(t) >= 35:
            return True
    return False

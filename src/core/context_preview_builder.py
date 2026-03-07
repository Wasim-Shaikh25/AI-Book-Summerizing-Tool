from __future__ import annotations

from typing import List, Sequence

from .models import NormalizedLine


def build_context_preview(lines: Sequence[NormalizedLine], idx: int) -> str:
    """
    Exact format required by spec:

    line_before_3
    line_before_2
    line_before_1

    >>> DETECTED_HEADING: TEXT <<<

    line_after_1
    line_after_2
    line_after_3

    ZERO text loss: do not strip or truncate any line content.
    """
    def _get(i: int) -> str:
        if 0 <= i < len(lines):
            return lines[i].text
        return ""

    before = [_get(idx - 3), _get(idx - 2), _get(idx - 1)]
    detected = _get(idx)
    after = [_get(idx + 1), _get(idx + 2), _get(idx + 3)]

    parts: List[str] = []
    parts.extend(before)
    parts.append("")
    parts.append(f">>> DETECTED_HEADING: {detected} <<<")
    parts.append("")
    parts.extend(after)
    return "\n".join(parts)

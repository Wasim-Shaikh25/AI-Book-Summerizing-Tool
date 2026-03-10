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
    def _get_valid_lines(start: int, end: int, exclude_idx: int = None) -> List[str]:
        result = []
        for i in range(start, end):
            if 0 <= i < len(lines) and (exclude_idx is None or i != exclude_idx):
                txt = lines[i].text
                if len(txt.strip()) >= 5:
                    result.append(txt)
        return result

    # Collect 5 valid lines before
    before = []
    i = idx - 1
    while len(before) < 5 and i >= 0:
        txt = lines[i].text
        if len(txt.strip()) >= 5:
            before.insert(0, txt)
        i -= 1

    # Collect 5 valid lines after
    after = []
    i = idx + 1
    while len(after) < 5 and i < len(lines):
        txt = lines[i].text
        if len(txt.strip()) >= 5:
            after.append(txt)
        i += 1

    detected = lines[idx].text if 0 <= idx < len(lines) else ""

    parts: List[str] = []
    parts.extend(before)
    parts.append("")
    parts.append(f">>> DETECTED_HEADING: {detected} <<<")
    parts.append("")
    parts.extend(after)
    return "\n".join(parts)

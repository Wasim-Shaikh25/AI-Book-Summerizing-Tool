from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from .context_preview_builder import build_context_preview
from .models import HeadingCandidate, NormalizedLine


_NUMERIC_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s*[\)\.\-:]?\s+\S.+$")
_ROMAN_RE = re.compile(
    r"^\s*(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})"
    r"(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\s*[\)\.\-:]?\s+\S.+$",
    re.IGNORECASE,
)


def _score_line(ln: NormalizedLine) -> Tuple[int, Dict[str, Any]]:
    text = ln.text or ""
    stripped = text.strip()

    reasons: Dict[str, Any] = {"signals": []}
    score = 0

    if _NUMERIC_RE.match(stripped):
        score += 3
        reasons["signals"].append("+3 numeric_heading")
    if _ROMAN_RE.match(stripped):
        score += 2
        reasons["signals"].append("+2 roman_heading")
    if ln.is_bold:
        score += 2
        reasons["signals"].append("+2 bold")
    if ln.large_font:
        score += 2
        reasons["signals"].append("+2 large_font")
    if ln.centered:
        score += 2
        reasons["signals"].append("+2 centered")
    if ln.large_gap:
        score += 2
        reasons["signals"].append("+2 large_gap")
    if len(stripped) < 120:
        score += 1
        reasons["signals"].append("+1 short_line")

    # Margin penalty
    if ln.page_height > 0 and (ln.y_pos < ln.page_height * 0.07 or ln.y_pos > ln.page_height * 0.93):
        score -= 2
        reasons["signals"].append("-2 margin_zone")

    reasons["score"] = score
    return score, reasons


def collect_candidates_scored(
    lines: Sequence[NormalizedLine],
    *,
    threshold: int = 3,
) -> Tuple[List[HeadingCandidate], List[Dict[str, Any]]]:
    """
    Candidate heading detector per spec:
      - Skip noise lines
      - Score using layout signals
      - Select if score >= threshold

    Returns:
      (candidates, scoring_log)
    """
    candidates: List[HeadingCandidate] = []
    scoring_log: List[Dict[str, Any]] = []

    for i, ln in enumerate(lines):
        if ln.is_noise:
            continue

        score, reasons = _score_line(ln)
        decision = "candidate" if score >= threshold else "reject"

        scoring_log.append(
            {
                "line_id": ln.line_id,
                "text": ln.text,
                "page_number": ln.page_number,
                "score": score,
                "signals": [str(s).replace("+", "").strip() for s in (reasons.get("signals", []) or [])],
                "selected": decision == "candidate",
                "score_breakdown": {},
                "context_preview": build_context_preview(lines, i),
                "bbox": [0.0, 0.0, 0.0, 0.0],
                "font_size": ln.font_size,
                "bold": ln.is_bold,
                "centered": ln.centered,
                "large_gap": ln.large_gap,
            }
        )

        if decision != "candidate":
            continue

        # Candidate id matches prior style: L{idx}:{prefix}
        compact = re.sub(r"\s+", " ", (ln.text or "").strip())
        cid = f"L{i}:{compact[:60]}"

        preview = build_context_preview(lines, i)
        # before/after for convenience; keep deterministic
        before = [lines[j].text if 0 <= j < len(lines) else "" for j in (i - 3, i - 2, i - 1)]
        after = [lines[j].text if 0 <= j < len(lines) else "" for j in (i + 1, i + 2, i + 3)]

        candidates.append(
            HeadingCandidate(
                id=cid,
                text=ln.text,
                start_line=i,
                end_line=i,
                before_context=before,
                after_context=after,
                full_context_preview=preview,
            )
        )

    return candidates, scoring_log

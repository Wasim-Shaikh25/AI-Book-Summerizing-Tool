from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from src.shared.models import Fragment, FinalHeading, HeadingCandidate, NormalizedLine


@dataclass(frozen=True, slots=True)
class BuildFragmentsResult:
    fragments: List[Fragment]
    heading_to_fragment_id: Dict[str, str]


def _to_lines(normalized: Sequence[NormalizedLine]) -> List[str]:
    # Build fragments from NormalizedLine to keep line_id alignment and filter noise.
    return [ln.text for ln in normalized]


def _join_lines(lines: Sequence[str]) -> str:
    return "\n".join(lines)


def _normalize_fragment_text(lines: Sequence[str]) -> str:
    """
    Normalize fragment text:
      - join with newlines
      - strip leading/trailing whitespace
      - drop leading/trailing empty lines
    """
    # First, trim each line's trailing spaces to avoid accidental padding.
    cleaned_lines = [ln.rstrip() for ln in lines]

    # Drop leading/trailing empty lines.
    while cleaned_lines and cleaned_lines[0].strip() == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1].strip() == "":
        cleaned_lines.pop()

    text = "\n".join(cleaned_lines).strip()
    return text


def _fragment_stats(text: str) -> Dict[str, int]:
    t = text or ""
    non_empty_lines = [ln for ln in t.splitlines() if ln.strip() != ""]
    words = [w for w in t.split() if w.strip() != ""]
    return {
        "fragment_chars": len(t),
        "fragment_lines": len(non_empty_lines),
        "fragment_words": len(words),
    }


def build_fragments(
    normalized: Sequence[NormalizedLine],
    headings: Sequence[HeadingCandidate | FinalHeading],
) -> Tuple[BuildFragmentsResult, List[Dict[str, Any]]]:
    """
    Unified fragment builder (no micro-merge).

    Policy:
      - Only create fragments for headings where (is_valid==True AND is_toc==False)
      - Fragment range: from heading.end_line+1 to next kept heading.start_line-1
      - Deterministic ordering by (start_line, end_line, id)

    Returns:
      (result, log_payload_for_07_fragments_json)
    """
    lines = _to_lines(normalized)

    def _line_start(h: HeadingCandidate | FinalHeading) -> int:
        # HeadingCandidate has (start_line/end_line). FinalHeading currently only has line_id.
        return int(getattr(h, "start_line", None) or getattr(h, "line_id", None) or 0)

    def _line_end(h: HeadingCandidate | FinalHeading) -> int:
        return int(getattr(h, "end_line", None) or getattr(h, "line_id", None) or 0)

    kept_sorted = sorted(
        list(headings),
        key=lambda h: (
            _line_start(h),
            _line_end(h),
            getattr(h, "id", ""),
        ),
    )

    fragments: List[Fragment] = []
    mapping: Dict[str, str] = {}
    log: List[Dict[str, Any]] = []

    for idx, h in enumerate(kept_sorted):
        # Fragment policy: content starts AFTER the heading line.
        start = max(0, _line_end(h) + 1)
        next_start = _line_start(kept_sorted[idx + 1]) if idx + 1 < len(kept_sorted) else len(lines)
        end_candidate = next_start - 1

        # If headings are adjacent (or overlapping), end_candidate can be < start.
        # Normalize so we never emit inverted ranges (start_line > end_line).
        end = end_candidate if end_candidate >= start else start

        frag_lines: List[str] = []
        if end_candidate >= start:
            for ln in normalized:
                if ln.line_id < start or ln.line_id > end_candidate:
                    continue
                if getattr(ln, "is_noise", False):
                    continue
                frag_lines.append(ln.text)

        frag_text = _normalize_fragment_text(frag_lines)

        # If there is no content between headings (or it all got filtered as noise),
        # we still keep a Fragment row for alignment, but its text should be empty.
        fid = f"F{idx}"
        fragments.append(
            Fragment(
                fragment_id=fid,
                start_line=start,
                end_line=end,
                text=frag_text,  # may be empty string
                assigned_heading_id=h.id,
            )
        )
        mapping[h.id] = fid

        stats = _fragment_stats(frag_text)
        log.append(
            {
                "heading_id": h.id,
                "heading_text": h.text,
                "fragment_id": fid,
                "start_line": start,
                "end_line": end,
                **stats,
            }
        )

    return BuildFragmentsResult(fragments=fragments, heading_to_fragment_id=mapping), log

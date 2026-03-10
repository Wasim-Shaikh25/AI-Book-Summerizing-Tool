from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import Fragment, HeadingCandidate, NormalizedLine


@dataclass(frozen=True, slots=True)
class BuildFragmentsResultV2:
    fragments: List[Fragment]
    heading_to_fragment_id: Dict[str, str]


def _to_lines(normalized: Sequence[NormalizedLine]) -> List[str]:
    # Backward compatible helper; build_fragments_v2 uses line_id-aware filtering
    # during fragment text assembly (so noise/TOC ranges can be excluded without
    # breaking start/end line_id boundaries).
    return [ln.text for ln in normalized]


def _join_lines(lines: Sequence[str]) -> str:
    return "\n".join(lines)


def _fragment_stats(text: str) -> Dict[str, int]:
    t = text or ""
    lines = [ln for ln in t.splitlines() if ln.strip() != ""]
    words = [w for w in t.split() if w.strip() != ""]
    return {
        "fragment_chars": len(t),
        "fragment_lines": len(lines),
        "fragment_words": len(words),
    }


def build_fragments_v2(
    normalized: Sequence[NormalizedLine],
    headings: Sequence[HeadingCandidate],
) -> Tuple[BuildFragmentsResultV2, List[Dict[str, Any]]]:
    """
    Spec-aligned fragment builder:
      - Only create fragments for headings where (is_valid==True AND is_toc==False)
      - Fragment range: from heading.end_line+1 to next kept heading.start_line-1
      - Deterministic ordering by (start_line, end_line, id)
    Returns:
      (result, log_payload_for_07_fragments_json)
    """
    lines = _to_lines(normalized)

    # NOTE: resolve_toc_sections() runs before this stage and removes TOC blocks.
    # We exclude noise lines during text assembly; TOC blocks are excluded because the
    # TOC headings are removed from the headings list (so fragments are only created for
    # non-TOC headings).
    kept = [h for h in headings if h.is_valid is True and h.is_toc is False]
    kept_sorted = sorted(kept, key=lambda h: (h.start_line, h.end_line, h.id))

    fragments: List[Fragment] = []
    mapping: Dict[str, str] = {}
    log: List[Dict[str, Any]] = []

    for idx, h in enumerate(kept_sorted):
        start = h.end_line + 1
        end = (kept_sorted[idx + 1].start_line - 1) if idx + 1 < len(kept_sorted) else (len(lines) - 1)
        if start < 0:
            start = 0
        # Build fragment text from NormalizedLine to keep line_id alignment and filter noise.
        frag_lines: List[str] = []
        if end >= start:
            for ln in normalized:
                if ln.line_id < start or ln.line_id > end:
                    continue
                if getattr(ln, "is_noise", False):
                    continue
                frag_lines.append(ln.text)

        frag_text = _join_lines(frag_lines)
        fid = f"F{idx}"
        fragments.append(
            Fragment(
                fragment_id=fid,
                start_line=start,
                end_line=end,
                text=frag_text if frag_text != "" else " ",  # avoid empty fragments downstream
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

    return BuildFragmentsResultV2(fragments=fragments, heading_to_fragment_id=mapping), log

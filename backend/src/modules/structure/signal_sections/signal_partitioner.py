"""Signal partitioner — turn boundary headings into sections with inner headings.

For each pair of adjacent boundary headings ``(b_i, b_{i+1})``:
    * section heading = ``b_i.text`` (verbatim from PDF)
    * section body    = joined line text from ``b_i.line_id + 1`` .. ``b_{i+1}.line_id - 1``
    * inner_headings  = every validated heading whose ``line_id`` falls inside
                        ``(b_i.line_id, b_{i+1}.line_id)`` and is NOT itself a boundary.
                        Each carries its score + page so the rewrite LLM can
                        judge real vs. noise.

No LLM. No PDF heading text is rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.shared.models import NormalizedLine
from src.modules.structure.signal_sections.signal_classifier import BoundaryHeading


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _line_text_by_id(lines: Sequence[NormalizedLine]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if isinstance(lid, int):
            out[lid] = getattr(ln, "text", "") or ""
    return out


def _line_meta_by_id(lines: Sequence[NormalizedLine]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if isinstance(lid, int):
            out[lid] = {
                "page_number": getattr(ln, "page_number", None),
                "is_noise": bool(getattr(ln, "is_noise", False)),
            }
    return out


def _join_line_range(
    *,
    line_text: Dict[int, str],
    line_meta: Dict[int, Dict[str, Any]],
    start_line: int,
    end_line: int,
) -> str:
    """Concatenate non-noise lines, preserving paragraph spacing only between blocks."""
    if end_line < start_line:
        return ""
    parts: List[str] = []
    for lid in range(start_line, end_line + 1):
        meta = line_meta.get(lid)
        if meta and meta.get("is_noise"):
            continue
        text = (line_text.get(lid) or "").rstrip()
        if not text.strip():
            continue
        parts.append(text)
    return "\n".join(parts).strip()


@dataclass
class PartitionedSection:
    section_id: str
    heading: str
    page_number: Optional[int]
    line_id_start: int
    line_id_end: int
    body: str
    body_chars: int
    inner_headings: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "heading": self.heading,
            "page_number": self.page_number,
            "line_id_start": int(self.line_id_start),
            "line_id_end": int(self.line_id_end),
            "body": self.body,
            "body_chars": int(self.body_chars),
            "inner_headings": list(self.inner_headings),
        }


def build_sections(
    *,
    boundaries: Sequence[BoundaryHeading],
    validated_headings: Sequence[Dict[str, Any]],
    lines: Sequence[NormalizedLine],
    drop_empty: bool = True,
) -> List[PartitionedSection]:
    """Build sections from boundary headings.

    Args:
        boundaries: sorted by ``line_id`` (output of ``pick_boundary_line_ids``).
        validated_headings: rows from ``stage_finalize_heading_list``
            (``ctx.final_headings_2_items``). Used to collect inner headings.
        lines: normalized layout lines (``ctx.lines``).
        drop_empty: skip sections with no body and no inner headings.
    """
    if not boundaries:
        return []

    line_text = _line_text_by_id(lines)
    line_meta = _line_meta_by_id(lines)

    boundary_lids = {int(b.line_id) for b in boundaries}

    # Pre-index validated headings by line_id (text + page + scoring hint).
    validated_by_lid: Dict[int, Dict[str, Any]] = {}
    for h in validated_headings or []:
        if not isinstance(h, dict):
            continue
        lid = h.get("line_id")
        if not isinstance(lid, int):
            continue
        validated_by_lid[int(lid)] = h

    # Section spans
    max_line_id = max(line_text.keys(), default=0)
    sections: List[PartitionedSection] = []
    sorted_boundaries = sorted(boundaries, key=lambda b: int(b.line_id))

    for i, b in enumerate(sorted_boundaries):
        start = int(b.line_id) + 1
        if i + 1 < len(sorted_boundaries):
            end = int(sorted_boundaries[i + 1].line_id) - 1
        else:
            end = max_line_id
        body = _join_line_range(
            line_text=line_text,
            line_meta=line_meta,
            start_line=start,
            end_line=end,
        )

        inner: List[Dict[str, Any]] = []
        for lid in range(start, end + 1):
            if lid in boundary_lids:
                continue
            head = validated_by_lid.get(lid)
            if head is None:
                continue
            text = _norm(str(head.get("text") or ""))
            if not text:
                continue
            confidence = head.get("confidence")
            signals = head.get("signals_used") or []
            reason = head.get("reason")
            inner.append(
                {
                    "text": text,
                    "line_id": int(lid),
                    "page_number": head.get("page_number"),
                    "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
                    "signals_used": list(signals) if isinstance(signals, list) else [],
                    "reason": reason,
                }
            )

        section = PartitionedSection(
            section_id=f"S{i + 1}",
            heading=b.text,
            page_number=b.page_number,
            line_id_start=int(b.line_id),
            line_id_end=end,
            body=body,
            body_chars=len(body),
            inner_headings=inner,
        )
        if drop_empty and not body and not inner:
            continue
        sections.append(section)

    # Renumber section ids contiguously after any drops
    for idx, sec in enumerate(sections, start=1):
        sec.section_id = f"S{idx}"
    return sections

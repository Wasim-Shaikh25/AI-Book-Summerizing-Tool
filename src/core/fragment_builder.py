from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Fragment, HeadingCandidate, NormalizedLine


@dataclass(frozen=True, slots=True)
class BuildFragmentsResult:
    fragments: List[Fragment]
    heading_to_fragment_id: Dict[str, str]
    pre_merge_log: str
    post_merge_log: str


def _to_lines(normalized: Sequence[NormalizedLine] | Sequence[str]) -> List[str]:
    if len(normalized) == 0:
        return []
    if isinstance(normalized[0], NormalizedLine):  # type: ignore[index]
        return [ln.text for ln in normalized]  # type: ignore[union-attr]
    return [str(x) for x in normalized]


def _join_lines(lines: Sequence[str]) -> str:
    # ZERO text loss policy: do not strip; preserve line order; re-add newline separators.
    return "\n".join(lines)


def _build_provisional_fragments(
    lines: Sequence[str], candidates: Sequence[HeadingCandidate]
) -> Tuple[List[Fragment], Dict[str, str], List[Tuple[str, int, int]]]:
    """
    Build fragments between ALL detected heading candidates (permissive / pre-validation).
    Returns:
      - fragments
      - heading_id -> fragment_id mapping
      - spans: list of (heading_id, start_line, end_line) for diagnostics/merge stage
    """
    sorted_cands = sorted(candidates, key=lambda c: (c.start_line, c.end_line, c.id))
    fragments: List[Fragment] = []
    mapping: Dict[str, str] = {}
    spans: List[Tuple[str, int, int]] = []

    if len(lines) == 0:
        return fragments, mapping, spans

    if len(sorted_cands) == 0:
        frag_id = "F0"
        fragments.append(
            Fragment(
                fragment_id=frag_id,
                start_line=0,
                end_line=max(0, len(lines) - 1),
                text=_join_lines(lines),
                assigned_heading_id=None,
            )
        )
        spans.append(("", 0, max(0, len(lines) - 1)))
        return fragments, mapping, spans

    for idx, cand in enumerate(sorted_cands):
        start = cand.end_line + 1
        end = (sorted_cands[idx + 1].start_line - 1) if idx + 1 < len(sorted_cands) else (len(lines) - 1)
        if start < 0:
            start = 0
        if end < start:
            # Empty fragment (still allowed, but keep as empty to preserve mapping + distribution)
            frag_lines: List[str] = []
        else:
            frag_lines = list(lines[start : end + 1])

        frag_id = f"F{idx}"
        fragments.append(
            Fragment(
                fragment_id=frag_id,
                start_line=start,
                end_line=end,
                text=_join_lines(frag_lines),
                assigned_heading_id=cand.id,
            )
        )
        mapping[cand.id] = frag_id
        spans.append((cand.id, start, end))

    return fragments, mapping, spans


def _format_fragments_log(
    title: str, fragments: Sequence[Fragment], heading_to_fragment_id: Dict[str, str]
) -> str:
    lines: List[str] = [title]
    lines.append(f"fragments={len(fragments)} headings_mapped={len(heading_to_fragment_id)}")
    for f in fragments:
        lines.append(
            f"- fragment_id={f.fragment_id} start={f.start_line} end={f.end_line} "
            f"assigned_heading_id={f.assigned_heading_id} text_len={len(f.text)}"
        )
    return "\n".join(lines)


def build_fragments(
    normalized: Sequence[NormalizedLine] | Sequence[str],
    headings: Sequence[HeadingCandidate],
) -> BuildFragmentsResult:
    """
    Fragment builder with ZERO text loss.

    STEP 1 (pre-filter assessment):
      - Build provisional fragments between ALL detected heading candidates.

    STEP 2 (post validation merge):
      - If some headings are marked is_valid=False, merge their fragment text into the
        nearest valid heading above (or next valid heading below if none above).
      - If no valid headings exist at all, use a synthetic heading 'Document Root'.

    Returns:
      BuildFragmentsResult:
        - fragments
        - heading_to_fragment_id
        - pre_merge_log
        - post_merge_log
    """
    lines = _to_lines(normalized)

    # STEP 1 — provisional fragments across ALL candidates (even before validation)
    provisional_fragments, provisional_mapping, _spans = _build_provisional_fragments(lines, headings)
    pre_log = _format_fragments_log("PRE_MERGE (provisional fragments)", provisional_fragments, provisional_mapping)

    # Determine validity
    sorted_heads = sorted(headings, key=lambda h: (h.start_line, h.end_line, h.id))
    valid_ids = [h.id for h in sorted_heads if h.is_valid is True]
    invalid_ids = [h.id for h in sorted_heads if h.is_valid is False]
    unknown_ids = [h.id for h in sorted_heads if h.is_valid is None]

    # If validation has not run yet (all None), return provisional (assessment complete)
    if len(valid_ids) == 0 and len(invalid_ids) == 0 and len(unknown_ids) > 0:
        post_log = _format_fragments_log(
            "POST_MERGE (no validation yet; returned provisional fragments)",
            provisional_fragments,
            provisional_mapping,
        )
        return BuildFragmentsResult(
            fragments=list(provisional_fragments),
            heading_to_fragment_id=dict(provisional_mapping),
            pre_merge_log=pre_log,
            post_merge_log=post_log,
        )

    # If no valid headings exist, create synthetic "Document Root" and merge everything into it.
    if len(valid_ids) == 0:
        root_heading_id = "Document Root"
        combined_text = _join_lines(lines)
        root_fragment = Fragment(
            fragment_id="F_ROOT",
            start_line=0,
            end_line=max(0, len(lines) - 1),
            text=combined_text,
            assigned_heading_id=root_heading_id,
        )
        post_log = _format_fragments_log(
            "POST_MERGE (no valid headings; synthetic Document Root)",
            [root_fragment],
            {root_heading_id: root_fragment.fragment_id},
        )
        return BuildFragmentsResult(
            fragments=[root_fragment],
            heading_to_fragment_id={root_heading_id: root_fragment.fragment_id},
            pre_merge_log=pre_log,
            post_merge_log=post_log,
        )

    # Build a quick lookup: heading_id -> fragment
    id_to_fragment: Dict[str, Fragment] = {}
    for f in provisional_fragments:
        if f.assigned_heading_id:
            id_to_fragment[f.assigned_heading_id] = f

    # Helper: find merge target for an invalid heading id
    valid_positions = {h.id: idx for idx, h in enumerate(sorted_heads) if h.is_valid is True}

    def _find_target_heading_id(invalid_heading_index: int) -> str:
        # nearest valid above
        for j in range(invalid_heading_index - 1, -1, -1):
            if sorted_heads[j].is_valid is True:
                return sorted_heads[j].id
        # else nearest valid below
        for j in range(invalid_heading_index + 1, len(sorted_heads)):
            if sorted_heads[j].is_valid is True:
                return sorted_heads[j].id
        # should never happen because we already handled no-valid case
        return valid_ids[0]

    # Start with one merged fragment per valid heading, initially its own provisional text.
    merged_text_by_valid: Dict[str, List[str]] = {vid: [] for vid in valid_ids}

    # Populate with valid heading fragments first (preserve text as-is)
    for vid in valid_ids:
        frag = id_to_fragment.get(vid)
        if frag is None:
            # Valid heading might map to empty range; keep empty.
            merged_text_by_valid[vid] = []
        else:
            merged_text_by_valid[vid] = frag.text.split("\n") if frag.text != "" else []

    # Merge invalid fragments into nearest valid heading above (else below)
    for idx, h in enumerate(sorted_heads):
        if h.is_valid is not False:
            continue
        invalid_frag = id_to_fragment.get(h.id)
        if invalid_frag is None:
            continue
        target_id = _find_target_heading_id(idx)
        # Append invalid text to target, preserving ordering relative to headings list:
        # We are iterating in document order, so this preserves deterministic merge order.
        if invalid_frag.text != "":
            merged_text_by_valid[target_id].extend(invalid_frag.text.split("\n"))

    # Any headings that are None (unknown) are treated as "kept provisional" and their fragments
    # should remain attached to themselves (i.e., not merged away).
    # This maintains STEP1 safety when validation is partial.
    for h in sorted_heads:
        if h.is_valid is None:
            frag = id_to_fragment.get(h.id)
            if frag is None:
                continue
            # Create a dedicated merged bucket for this unknown heading id
            if h.id not in merged_text_by_valid:
                merged_text_by_valid[h.id] = frag.text.split("\n") if frag.text != "" else []

    # Build final fragments list + mapping.
    final_fragments: List[Fragment] = []
    heading_to_fragment_id: Dict[str, str] = {}

    # Preserve heading order in output fragments: valid headings + unknown headings in original order.
    output_heading_ids: List[str] = []
    for h in sorted_heads:
        if h.is_valid is True or h.is_valid is None:
            if h.id not in output_heading_ids:
                output_heading_ids.append(h.id)

    for out_idx, hid in enumerate(output_heading_ids):
        bucket = merged_text_by_valid.get(hid, [])
        # Determine range as best-effort from provisional fragment; no trimming.
        src_frag: Optional[Fragment] = id_to_fragment.get(hid)
        if src_frag is None:
            start_line = 0
            end_line = max(0, len(lines) - 1)
        else:
            start_line = src_frag.start_line
            end_line = src_frag.end_line

        fid = f"F_M{out_idx}"

        # Safety: integration tests require no empty fragment text.
        # Keep ZERO text-loss policy by falling back to the exact line-span slice
        # when the merge bucket is empty (this can happen when consecutive headings
        # have no body lines between them).
        text = _join_lines(bucket)
        if text == "" and len(lines) > 0:
            if start_line <= end_line:
                text = _join_lines(lines[start_line : end_line + 1])
            else:
                # No body lines for this heading. Keep fragment non-empty by using the heading
                # line itself (last resort). This preserves determinism and avoids empty output.
                # Note: this is NOT introducing new text; it reuses existing PDF-extracted text.
                heading_line_index = max(0, min(len(lines) - 1, start_line - 1))
                text = lines[heading_line_index]

        final_fragments.append(
            Fragment(
                fragment_id=fid,
                start_line=start_line,
                end_line=end_line,
                text=text,
                assigned_heading_id=hid,
            )
        )
        heading_to_fragment_id[hid] = fid

    post_log = _format_fragments_log("POST_MERGE (after invalid merge)", final_fragments, heading_to_fragment_id)

    return BuildFragmentsResult(
        fragments=final_fragments,
        heading_to_fragment_id=heading_to_fragment_id,
        pre_merge_log=pre_log,
        post_merge_log=post_log,
    )

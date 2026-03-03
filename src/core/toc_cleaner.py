from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from src.ai.gemini_adapter import gemini_generate
from .models import FinalHeading, Fragment


_TOC_SYSTEM_INSTRUCTION = (
    "You are detecting whether a heading is coming from a PDF Table of Contents (TOC) "
    "or is a real section heading in the main body.\n"
    "Return ONLY a JSON object: {\"is_toc\": true/false}.\n"
    "No explanations, no markdown, no extra keys."
)


def _ensure_toc_trace_dir() -> Path:
    base = Path("logs") / "toc_trace"
    base.mkdir(parents=True, exist_ok=True)
    # Keep it simple: one rolling trace file (no extra folders)
    return base


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_fragment_text_by_id(
    fragments: Sequence[Fragment] | None,
    fragment_text_by_id: Dict[str, str] | None,
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if fragment_text_by_id is not None:
        out.update(fragment_text_by_id)
    if fragments is not None:
        for f in fragments:
            out[f.fragment_id] = f.text
    return out


def _normalize_heading_key(text: str) -> str:
    # Drop "L123:" prefix if present, lowercase, collapse spaces.
    t = text.strip()
    if ":" in t and t.split(":", 1)[0].startswith("L") and t.split(":", 1)[0][1:].isdigit():
        t = t.split(":", 1)[1].strip()
    t = " ".join(t.split()).lower()
    return t


def _fragment_lines(text: str) -> int:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return len(lines)


def _frag_text(h: FinalHeading, text_by_fragment_id: Dict[str, str]) -> str:
    if not h.fragment_id:
        return ""
    return text_by_fragment_id.get(h.fragment_id, "")


def _dedupe_keep_stronger(
    headings: Sequence[FinalHeading],
    text_by_fragment_id: Dict[str, str],
) -> Tuple[List[FinalHeading], List[Dict], Dict[str, bool]]:
    """
    Remove duplicate headings (same normalized text). Keep the one with more fragment text.

    IMPORTANT:
      This is phase-1. We only decide which instance to KEEP.
      The kept heading will be the only one considered in the Gemini TOC phase,
      so we don't accidentally evaluate/remove both duplicates.

    Returns (kept_headings, removals_log).
    """
    key_to_best: Dict[str, FinalHeading] = {}
    key_to_best_len: Dict[str, int] = {}
    removed: List[Dict] = []
    # Only mark keys as "evaluated_by_dedupe" if duplicates actually existed for that key.
    evaluated_by_dedupe: Dict[str, bool] = {}

    for h in headings:
        key = _normalize_heading_key(h.text)
        cur_len = len(_frag_text(h, text_by_fragment_id))
        if key not in key_to_best or cur_len > key_to_best_len[key]:
            if key in key_to_best:
                evaluated_by_dedupe[key] = True
                prev = key_to_best[key]
                removed.append(
                    {
                        "removed_id": prev.id,
                        "kept_id": h.id,
                        "reason": "duplicate_weaker",
                        "heading_key": key,
                        "removed_fragment_chars": key_to_best_len[key],
                        "kept_fragment_chars": cur_len,
                    }
                )
            key_to_best[key] = h
            key_to_best_len[key] = cur_len
        else:
            evaluated_by_dedupe[key] = True
            removed.append(
                {
                    "removed_id": h.id,
                    "kept_id": key_to_best[key].id,
                    "reason": "duplicate_weaker",
                    "heading_key": key,
                    "removed_fragment_chars": cur_len,
                    "kept_fragment_chars": key_to_best_len[key],
                }
            )

    # Preserve original order of kept headings
    kept_ids = {h.id for h in key_to_best.values()}
    kept_ordered = [h for h in headings if h.id in kept_ids]
    return kept_ordered, removed, evaluated_by_dedupe


def _gemini_is_toc(heading_text: str, content_preview: str) -> bool:
    user_prompt = json.dumps(
        {
            "heading": heading_text,
            "content_preview": content_preview,
            "task": "Decide if this heading is from TOC (true) or a real body heading (false).",
        },
        ensure_ascii=False,
    )
    resp = gemini_generate(_TOC_SYSTEM_INSTRUCTION, user_prompt)
    if isinstance(resp.parsed_json, dict) and isinstance(resp.parsed_json.get("is_toc"), bool):
        return bool(resp.parsed_json["is_toc"])
    return False  # safe default


def clean_toc(
    headings: Sequence[FinalHeading],
    fragments: Sequence[Fragment] | None = None,
    *,
    fragment_text_by_id: Dict[str, str] | None = None,
    min_fragment_chars: int = 20,
    min_lines_after_heading: int = 3,
    enable_gemini_toc_check: bool = True,
) -> List[FinalHeading]:
    """
    Removes TOC-only entries after heading filtering.

    Steps (simple, debug-friendly):
      1) Remove duplicate headings (same normalized text); keep the one with more fragment text.
      2) For remaining headings with low content (lines < min_lines_after_heading or chars < min_fragment_chars),
         optionally ask Gemini if it's a TOC heading; if yes, remove it.

    Notes:
      - Fragment text can be provided via `fragments` or `fragment_text_by_id`.
      - If no fragment text is available, this function is a no-op.
      - Never removes the first heading (conservative).
    """
    if len(headings) <= 1:
        return list(headings)

    text_by_fragment_id = _build_fragment_text_by_id(fragments, fragment_text_by_id)
    if not text_by_fragment_id:
        return list(headings)

    trace_dir = _ensure_toc_trace_dir()
    removals: List[Dict] = []

    # Step 1: de-dupe by normalized heading text, keep stronger content.
    deduped, removed_dupes, evaluated_by_dedupe = _dedupe_keep_stronger(headings, text_by_fragment_id)
    removals.extend(removed_dupes)

    # Step 2: Gemini check for low-content headings (likely TOC rows that slipped through).
    # Only headings still "flagged" as low_content are evaluated here (simple 2-phase logic).
    cleaned: List[FinalHeading] = []
    cleaned.append(deduped[0])  # never remove first

    for h in deduped[1:]:
        frag_text = _frag_text(h, text_by_fragment_id)
        frag_chars = len(frag_text)
        frag_lines = _fragment_lines(frag_text)

        key = _normalize_heading_key(h.text)
        needs_eval = frag_lines < min_lines_after_heading or frag_chars < min_fragment_chars

        # If this heading-key had duplicates, consider it already “evaluated” by dedupe.
        # This prevents the (1.1 duplicate removed) + (kept 1.1 later removed by Gemini) double-processing pattern.
        if evaluated_by_dedupe.get(key, False):
            cleaned.append(h)
            continue

        if not needs_eval or not enable_gemini_toc_check:
            cleaned.append(h)
            continue

        preview = frag_text.strip()[:900]
        is_toc = _gemini_is_toc(h.text, preview)
        # evaluated once -> flag is effectively cleared by decision (keep/remove)
        if is_toc:
            removals.append(
                {
                    "removed_id": h.id,
                    "reason": "gemini_toc",
                    "fragment_chars": frag_chars,
                    "fragment_lines": frag_lines,
                }
            )
            continue

        cleaned.append(h)

    # Trace (single file, easy to diff)
    _write_json(
        trace_dir / "toc_removals.json",
        {
            "removed": removals,
            "final_count": len(cleaned),
        },
    )

    return cleaned

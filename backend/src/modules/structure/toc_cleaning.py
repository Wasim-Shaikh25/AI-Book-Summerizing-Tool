from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from src.shared.models import FinalHeading, Fragment


def _ensure_toc_trace_dir() -> Path:
    base = Path("logs") / "toc_trace"
    base.mkdir(parents=True, exist_ok=True)
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
    Returns (kept_headings, removals_log, evaluated_by_dedupe).
    """
    key_to_best: Dict[str, FinalHeading] = {}
    key_to_best_len: Dict[str, int] = {}
    removed: List[Dict] = []
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

    kept_ids = {h.id for h in key_to_best.values()}
    kept_ordered = [h for h in headings if h.id in kept_ids]
    return kept_ordered, removed, evaluated_by_dedupe


def clean_toc(
    headings: Sequence[FinalHeading],
    fragments: Sequence[Fragment] | None = None,
    *,
    fragment_text_by_id: Dict[str, str] | None = None,
    _min_fragment_chars: int = 20,
    _min_lines_after_heading: int = 3,
) -> List[FinalHeading]:
    """
    Identity pass: headings unchanged. Helpers above remain for a future non-identity implementation.
    """
    return list(headings)

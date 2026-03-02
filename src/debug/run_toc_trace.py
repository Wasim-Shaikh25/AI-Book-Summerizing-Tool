"""
Debug runner: end-to-end TOC trace with deterministic artifacts.

Goal (triage):
- Show what is sent to Gemini (heading validation request payload)
- Show what is received from Gemini (raw + parsed response)
- Show TOC after:
  1) candidate collection (raw)
  2) Gemini filtering (validated/filtered)
  3) fragment building
  4) hierarchy assignment
  5) TOC cleaning

This is intentionally a debug-only entrypoint. It does NOT try to "fix" logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.core.pdf_extractor import extract_pdf
from src.core.text_normalizer import normalize_text
from src.core.heading_candidate_collector import collect_heading_candidates
from src.core.heading_validator import validate_headings
from src.core.fragment_builder import build_fragments
from src.core.hierarchy_assigner import assign_hierarchy
from src.core.models import FinalHeading
from src.core.toc_cleaner import clean_toc


def _to_jsonable(x: Any) -> Any:
    if is_dataclass(x):
        return asdict(x)
    if isinstance(x, dict):
        return {k: _to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_to_jsonable(v) for v in x]
    return x


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _preview_lines(items: Iterable[Any], n: int = 15) -> list[Any]:
    out = []
    for i, it in enumerate(items):
        if i >= n:
            break
        out.append(_to_jsonable(it))
    return out


def run(pdf_path: str) -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("logs") / "toc_trace" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_doc = extract_pdf(pdf_path)
    normalized = normalize_text(pdf_doc)

    candidates = collect_heading_candidates(normalized)
    _write_json(out_dir / "01_heading_candidates_raw.preview.json", _preview_lines(candidates, 25))

    validated = validate_headings(list(candidates))
    valid_only = [h for h in validated if getattr(h, "is_valid", None) is True]
    _write_json(out_dir / "02_heading_candidates_valid.preview.json", _preview_lines(valid_only, 25))

    frag_result = build_fragments(normalized, validated)
    _write_json(out_dir / "03_fragments.preview.json", _preview_lines(frag_result.fragments, 25))
    (out_dir / "03_fragments.pre_merge_log.txt").write_text(frag_result.pre_merge_log, encoding="utf-8")
    (out_dir / "03_fragments.post_merge_log.txt").write_text(frag_result.post_merge_log, encoding="utf-8")

    # assign_hierarchy expects List[FinalHeading]
    final_heads = [
        FinalHeading(
            id=f.assigned_heading_id or f"UNASSIGNED:{f.fragment_id}",
            text=(f.assigned_heading_id or ""),
            level=1,
            fragment_id=f.fragment_id,
        )
        for f in frag_result.fragments
    ]
    hierarchy = assign_hierarchy(final_heads)
    _write_json(out_dir / "04_hierarchy.preview.json", _preview_lines(hierarchy, 40))

    toc = clean_toc(hierarchy, fragments=frag_result.fragments)
    _write_json(out_dir / "05_toc_cleaned.json", toc)

    return out_dir


if __name__ == "__main__":
    # Default to the repository reference PDF, but allow overriding:
    #   python -m src.debug.run_toc_trace "path\\to\\file.pdf"
    pdf = None
    import sys

    if len(sys.argv) > 1:
        pdf = sys.argv[1]
    else:
        pdf = os.getenv("PDF_PATH", "reference/law_of_tort.pdf")

    out = run(pdf)
    print(f"[+] TOC trace written to: {out}")

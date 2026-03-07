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
from src.core.logging.pipeline_logger import PipelineLogger
from src.core.fragment_builder import build_fragments
from src.core.hierarchy_assigner import assign_hierarchy
from src.core.models import FinalHeading
from src.core.noise_filter import mark_noise
from src.core.toc_classifier import classify_toc
from src.core.toc_section_resolver import resolve_toc_sections
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
    # Write ALL debug artifacts into the same deterministic pipeline run folder
    # (so you can inspect everything in one place alongside other stages).
    run_logger = PipelineLogger.create()
    out_dir = run_logger.run_dir

    pdf_doc = extract_pdf(pdf_path)
    normalized = normalize_text(pdf_doc)

    # Stage 02 equivalent: noise detection (never deletes lines)
    normalized, noise_log = mark_noise(normalized)
    _write_json(out_dir / "02_noise_filter.json", noise_log)

    candidates = collect_heading_candidates(normalized)
    _write_json(out_dir / "01_heading_candidates_raw.preview.json", _preview_lines(candidates, 25))

    # Use the same PipelineLogger so heading validation writes:
    #  - 05_gemini_request.json
    #  - 05_gemini_raw_response.json
    #  - 05_gemini_heading_validation.json
    validated = validate_headings(list(candidates), logger=run_logger)

    # Stage 06 equivalent: Gemini TOC classification (writes 06_gemini_toc_* files via PipelineLogger)
    validated = classify_toc(validated, logger=run_logger)

    valid_only = [h for h in validated if getattr(h, "is_valid", None) is True]
    _write_json(out_dir / "02_heading_candidates_valid.preview.json", _preview_lines(valid_only, 25))

    # Apply the same TOC resolver stage as the production pipeline.
    validated = resolve_toc_sections(validated, lines=normalized, logger=run_logger)

    frag_result = build_fragments(normalized, validated)
    _write_json(out_dir / "03_fragments.preview.json", _preview_lines(frag_result.fragments, 25))

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

    # TOC cleaning (currently disabled as a removal stage), but we still log a deterministic
    # per-run removals file so debugging is self-contained inside the run folder.
    toc_in = hierarchy
    toc_out = clean_toc(hierarchy, fragments=frag_result.fragments)

    removed_ids = sorted({h.id for h in toc_in} - {h.id for h in toc_out})
    _write_json(
        out_dir / "05_toc_removals.json",
        {
            "removed_count": len(removed_ids),
            "removed_ids": removed_ids,
            "kept_count": len(toc_out),
        },
    )

    _write_json(out_dir / "05_toc_cleaned.json", toc_out)

    print(f"[+] Debug run folder: {run_logger.run_dir}")
    return out_dir


if __name__ == "__main__":
    # Default to the repository reference PDF, but allow overriding:
    #   python -m src.debug.run_toc_trace "path\\to\\file.pdf"
    pdf = None
    import sys

    if len(sys.argv) > 1:
        pdf = sys.argv[1]
    else:
        # Default to a drop-in folder so you can copy/paste PDFs here for debugging:
        #   src/debug/pdf_files/<your.pdf>
        pdf = os.getenv("PDF_PATH", "src/debug/pdf_files/input.pdf")

    out = run(pdf)
    print(f"[+] TOC trace written to: {out}")

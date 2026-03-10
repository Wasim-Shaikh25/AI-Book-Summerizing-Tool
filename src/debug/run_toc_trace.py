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
from typing import Any, Iterable, Optional

import fitz  # PyMuPDF

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
    out: list[Any] = []
    for i, it in enumerate(items):
        if i >= n:
            break
        out.append(_to_jsonable(it))
    return out


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_line_boxes_from_normalized(pdf_path: str, normalized: list[Any]) -> list[dict[str, Any]]:
    """
    NormalizedLine doesn't store bbox, only y_pos/font_size and page_number.
    Build an approximate rectangle per line for visualization purposes.
    """
    doc = fitz.open(pdf_path)
    try:
        page_rects = {i + 1: doc.load_page(i).rect for i in range(len(doc))}
    finally:
        doc.close()

    layout_payload: list[dict[str, Any]] = []
    for ln in normalized:
        try:
            page_number = getattr(ln, "page_number", None)
            line_id = getattr(ln, "line_id", None)
            if not (isinstance(page_number, int) and isinstance(line_id, int)):
                continue

            pr = page_rects.get(page_number)
            if pr is None:
                continue

            y = float(getattr(ln, "y_pos", 0.0))
            fs = float(getattr(ln, "font_size", 10.0) or 10.0)

            x0 = 12.0
            x1 = float(getattr(pr, "width", pr.x1) - 12.0)
            y0 = max(0.0, y - fs * 0.9)
            y1 = min(float(getattr(pr, "height", pr.y1)), y + fs * 0.9)

            if x1 <= x0 or y1 <= y0:
                continue

            layout_payload.append(
                {
                    "line_id": line_id,
                    "page_number": page_number,
                    "bbox": [x0, y0, x1, y1],
                    "text": getattr(ln, "text", None),
                }
            )
        except Exception:
            continue

    return layout_payload


def visualize_pdf_structure(pdf_path: str, run_folder: Path) -> None:
    """
    Debug-only PDF overlay visualizer.

    Generates separate PDFs (so each layer is readable in isolation):
      - debug_overlay_noise.pdf
      - debug_overlay_candidates.pdf
      - debug_overlay_headings.pdf
      - debug_overlay_toc.pdf
      - debug_overlay_fragments.pdf
      - debug_overlay_all.pdf

    Missing JSON files are tolerated: that overlay layer is skipped.
    """
    layout = _read_json(run_folder / "01_layout_lines.json")
    noise = _read_json(run_folder / "02_noise_filter.json")

    # Prefer full artifacts (debug runner writes these), then fall back to previews.
    candidates = _read_json(run_folder / "03_candidate_scoring.json")
    if candidates is None:
        candidates = _read_json(run_folder / "01_heading_candidates_raw.json")
    if candidates is None:
        candidates = _read_json(run_folder / "01_heading_candidates_raw.preview.json")

    headings = _read_json(run_folder / "09_final_headings.json")
    if headings is None:
        headings = _read_json(run_folder / "02_heading_candidates_valid.json")
    if headings is None:
        headings = _read_json(run_folder / "02_heading_candidates_valid.preview.json")

    fragments = _read_json(run_folder / "07_fragments.json")
    if fragments is None:
        fragments = _read_json(run_folder / "03_fragments.json")
    if fragments is None:
        fragments = _read_json(run_folder / "03_fragments.preview.json")

    if not isinstance(layout, list) or len(layout) == 0:
        print("[!] visualize: missing/empty 01_layout_lines.json; skipping overlay (no coordinates).")
        return

    # line_id -> (page_idx, rect)
    line_boxes: dict[int, tuple[int, fitz.Rect]] = {}
    for it in layout:
        if not isinstance(it, dict):
            continue
        line_id = it.get("line_id")
        page_number = it.get("page_number")
        bbox = it.get("bbox")
        if not (isinstance(line_id, int) and isinstance(page_number, int) and isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            continue
        try:
            rect = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        except Exception:
            continue
        line_boxes[line_id] = (page_number - 1, rect)

    def apply_overlays(doc: fitz.Document, *, do_noise: bool, do_candidates: bool, do_headings: bool, do_toc: bool, do_fragments: bool) -> None:
        def draw_tag(page_idx: int, rect: fitz.Rect, label: str, rgb: tuple[float, float, float]) -> None:
            if page_idx < 0 or page_idx >= len(doc):
                return
            page = doc.load_page(page_idx)
            page.draw_rect(rect, color=rgb, width=2)
            y = max(rect.y0 - 6, 2)
            page.insert_text((rect.x0, y), label, fontsize=8, color=rgb)

        def draw_line_boxes(
            *,
            line_ids: Iterable[int],
            label: str,
            rgb: tuple[float, float, float],
        ) -> None:
            for lid in line_ids:
                box = line_boxes.get(lid)
                if not box:
                    continue
                page_idx, rect = box
                draw_tag(page_idx, rect, label, rgb)

        # NOISE (yellow)
        if do_noise and isinstance(noise, list):
            for it in noise:
                if not isinstance(it, dict):
                    continue
                if "summary" in it:
                    continue
                if it.get("decision") != "noise":
                    continue
                line_id = it.get("line_id")
                if not isinstance(line_id, int):
                    continue
                box = line_boxes.get(line_id)
                if not box:
                    continue
                page_idx, rect = box
                draw_tag(page_idx, rect, "NOISE", (1, 1, 0))

        # CANDIDATES (red)
        if do_candidates and isinstance(candidates, list):
            for it in candidates:
                if not isinstance(it, dict):
                    continue
                # production scoring format
                if "selected" in it:
                    if it.get("selected") is not True:
                        continue
                    line_id = it.get("line_id") or it.get("source_line_id")
                    if not isinstance(line_id, int):
                        continue
                    box = line_boxes.get(line_id)
                    if not box:
                        continue
                    page_idx, rect = box
                    draw_tag(page_idx, rect, "CANDIDATE", (1, 0, 0))
                    continue
                # debug preview HeadingCandidate format
                start_line = it.get("start_line")
                if isinstance(start_line, int):
                    box = line_boxes.get(start_line)
                    if not box:
                        continue
                    page_idx, rect = box
                    draw_tag(page_idx, rect, "CANDIDATE", (1, 0, 0))

        # HEADINGS / TOC
        if (do_headings or do_toc) and isinstance(headings, list):
            for it in headings:
                if not isinstance(it, dict):
                    continue
                is_toc = it.get("is_toc") is True
                if is_toc and not do_toc:
                    continue
                if (not is_toc) and not do_headings:
                    continue

                label = "TOC" if is_toc else "HEADING"
                color = (1, 0, 1) if is_toc else (0, 1, 0)

                line_id = it.get("line_id") or it.get("source_line_id")
                if isinstance(line_id, int):
                    box = line_boxes.get(line_id)
                    if not box:
                        continue
                    page_idx, rect = box
                    draw_tag(page_idx, rect, label, color)
                    continue

                start_line = it.get("start_line")
                if isinstance(start_line, int):
                    box = line_boxes.get(start_line)
                    if not box:
                        continue
                    page_idx, rect = box
                    draw_tag(page_idx, rect, label, color)

        # FRAGMENTS (blue)
        # Draw line-level boxes (not per-page union rectangles) so that exclusion is visually obvious:
        # if a heading/TOC/noise line is excluded, it will not have a blue box.
        if do_fragments and isinstance(fragments, list):
            covered_line_ids: set[int] = set()

            # noise coverage
            if isinstance(noise, list):
                for it in noise:
                    if not isinstance(it, dict):
                        continue
                    if "summary" in it:
                        continue
                    if it.get("decision") != "noise":
                        continue
                    lid = it.get("line_id")
                    if isinstance(lid, int):
                        covered_line_ids.add(lid)

            # heading/toc coverage (mark the heading start_line as covered)
            if isinstance(headings, list):
                for it in headings:
                    if not isinstance(it, dict):
                        continue
                    lid = it.get("line_id") or it.get("source_line_id") or it.get("start_line")
                    if isinstance(lid, int):
                        covered_line_ids.add(lid)

            for it in fragments:
                if not isinstance(it, dict):
                    continue
                fid = it.get("fragment_id") or it.get("id")
                start_line = it.get("start_line")
                end_line = it.get("end_line")
                if not (isinstance(fid, str) and isinstance(start_line, int) and isinstance(end_line, int)):
                    continue
                lo, hi = (start_line, end_line) if start_line <= end_line else (end_line, start_line)

                line_ids = [lid for lid in range(lo, hi + 1) if lid not in covered_line_ids]
                draw_line_boxes(line_ids=line_ids, label=f"FRAGMENT {fid}", rgb=(0, 0, 1))

    # Create per-layer PDFs
    outputs = [
        ("debug_overlay_noise.pdf", dict(do_noise=True, do_candidates=False, do_headings=False, do_toc=False, do_fragments=False)),
        ("debug_overlay_candidates.pdf", dict(do_noise=False, do_candidates=True, do_headings=False, do_toc=False, do_fragments=False)),
        ("debug_overlay_headings.pdf", dict(do_noise=False, do_candidates=False, do_headings=True, do_toc=False, do_fragments=False)),
        ("debug_overlay_toc.pdf", dict(do_noise=False, do_candidates=False, do_headings=False, do_toc=True, do_fragments=False)),
        ("debug_overlay_fragments.pdf", dict(do_noise=False, do_candidates=False, do_headings=False, do_toc=False, do_fragments=True)),
        # Validated structure view: noise + TOC + valid headings + residual fragments (no candidates)
        ("debug_overlay_validated_structure.pdf", dict(do_noise=True, do_candidates=False, do_headings=True, do_toc=True, do_fragments=True)),
        ("debug_overlay_all.pdf", dict(do_noise=True, do_candidates=True, do_headings=True, do_toc=True, do_fragments=True)),
    ]

    for filename, flags in outputs:
        doc = fitz.open(pdf_path)
        try:
            apply_overlays(doc, **flags)
            out_path = run_folder / filename
            doc.save(out_path.as_posix())
            print(f"[+] visualize: wrote {out_path}")
        finally:
            doc.close()


def run(pdf_path: str) -> Path:
    # Write ALL debug artifacts into the same deterministic pipeline run folder
    run_logger = PipelineLogger.create()
    out_dir = run_logger.run_dir

    pdf_doc = extract_pdf(pdf_path)
    normalized = normalize_text(pdf_doc)

    # Debug-only layout for visualization
    layout_payload = _build_line_boxes_from_normalized(pdf_path, normalized)
    _write_json(out_dir / "01_layout_lines.json", layout_payload)

    # Stage 02 equivalent: noise detection (never deletes lines)
    normalized, noise_log = mark_noise(normalized)
    _write_json(out_dir / "02_noise_filter.json", noise_log)

    candidates = collect_heading_candidates(normalized)
    # Write full list (so visualizer can annotate the entire PDF), plus a small preview for quick inspection.
    _write_json(out_dir / "01_heading_candidates_raw.json", candidates)
    _write_json(out_dir / "01_heading_candidates_raw.preview.json", _preview_lines(candidates, 25))

    # Use the same PipelineLogger so heading validation writes:
    #  - 05_gemini_request.json
    #  - 05_gemini_raw_response.json
    #  - 05_gemini_heading_validation.json
    validated = validate_headings(list(candidates), logger=run_logger)

    # Stage 06 equivalent: Gemini TOC classification (writes 06_gemini_toc_* files via PipelineLogger)
    validated = classify_toc(validated, logger=run_logger)

    valid_only = [h for h in validated if getattr(h, "is_valid", None) is True]
    # Write full list + preview.
    _write_json(out_dir / "02_heading_candidates_valid.json", valid_only)
    _write_json(out_dir / "02_heading_candidates_valid.preview.json", _preview_lines(valid_only, 25))

    # Apply the same TOC resolver stage as the production pipeline.
    validated = resolve_toc_sections(validated, lines=normalized, logger=run_logger)

    frag_result = build_fragments(normalized, validated)
    # Write full list + preview.
    _write_json(out_dir / "03_fragments.json", frag_result.fragments)
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
    hierarchy = assign_hierarchy(final_heads, logger=run_logger)
    _write_json(out_dir / "04_hierarchy.preview.json", _preview_lines(hierarchy, 40))

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
    # python -m src.debug.run_toc_trace "path\\to\\file.pdf" --visualize
    import sys

    visualize = "--visualize" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--visualize"]

    if len(args) > 0:
        pdf = args[0]
    else:
        pdf = os.getenv("PDF_PATH", "src/debug/pdf_files/input.pdf")

    out = run(pdf)
    print(f"[+] TOC trace written to: {out}")

    if visualize:
        visualize_pdf_structure(pdf, out)

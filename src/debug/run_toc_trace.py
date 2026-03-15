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
from src.core.layout_enrichment import lines_to_log
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

    toc = _read_json(run_folder / "05_gemini_toc_classification.json")
    if toc is None:
        toc = _read_json(run_folder / "05_gemini_toc_classification.preview.json")

    fragments = _read_json(run_folder / "07_fragments.json")
    if fragments is None:
        fragments = _read_json(run_folder / "03_fragments.json")
    if fragments is None:
        fragments = _read_json(run_folder / "03_fragments.preview.json")

    # PipelineLogger stage logs are dicts: {"items": [...]}.
    if isinstance(layout, dict) and isinstance(layout.get("items"), list):
        layout = layout["items"]
    if isinstance(noise, dict) and isinstance(noise.get("items"), list):
        noise = noise["items"]
    if isinstance(candidates, dict) and isinstance(candidates.get("items"), list):
        candidates = candidates["items"]
    if isinstance(headings, dict) and isinstance(headings.get("items"), list):
        headings = headings["items"]
    if isinstance(fragments, dict) and isinstance(fragments.get("items"), list):
        fragments = fragments["items"]
    if isinstance(toc, dict) and isinstance(toc.get("items"), list):
        toc = toc["items"]

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

        def _parse_line_id_from_heading_id(hid: Any) -> Optional[int]:
            # Examples:
            #  - "L60:Nature of Torts"
            #  - "L16:A. INTRODUCTION:"
            if not isinstance(hid, str):
                return None
            if not hid.startswith("L"):
                return None
            # split "L60:..." -> "60"
            try:
                num = hid[1:].split(":", 1)[0]
                return int(num)
            except Exception:
                return None

        # HEADINGS (green) from stage-09
        if do_headings and isinstance(headings, list):
            for it in headings:
                if not isinstance(it, dict):
                    continue

                line_id = it.get("line_id") or it.get("source_line_id")
                if not isinstance(line_id, int):
                    line_id = _parse_line_id_from_heading_id(it.get("heading_id"))

                if not isinstance(line_id, int):
                    continue

                box = line_boxes.get(line_id)
                if not box:
                    continue
                page_idx, rect = box
                draw_tag(page_idx, rect, "HEADING", (0, 1, 0))

        # TOC (magenta) from stage-05
        if do_toc and isinstance(toc, list):
            for it in toc:
                if not isinstance(it, dict):
                    continue
                if it.get("is_toc") is not True:
                    continue

                line_id = _parse_line_id_from_heading_id(it.get("heading_id"))
                if not isinstance(line_id, int):
                    continue

                box = line_boxes.get(line_id)
                if not box:
                    continue
                page_idx, rect = box
                draw_tag(page_idx, rect, "TOC", (1, 0, 1))

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
    # User-facing requested overlays (exactly 5 PDFs):
    # 1) noise marking
    # 2) qualified headings
    # 3) fragments
    # 4) toc
    # 5) overall
    outputs = [
        ("01_noise_marking.pdf", dict(do_noise=True, do_candidates=False, do_headings=False, do_toc=False, do_fragments=False)),
        ("02_qualified_headings.pdf", dict(do_noise=False, do_candidates=False, do_headings=True, do_toc=False, do_fragments=False)),
        ("03_fragments.pdf", dict(do_noise=False, do_candidates=False, do_headings=False, do_toc=False, do_fragments=True)),
        ("04_toc.pdf", dict(do_noise=False, do_candidates=False, do_headings=False, do_toc=True, do_fragments=False)),
        ("05_overall.pdf", dict(do_noise=True, do_candidates=False, do_headings=True, do_toc=True, do_fragments=True)),
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
    # Use the same centralized PipelineLogger contract as production:
    # only the 10 whitelisted JSON files under logs/run_<timestamp>/
    run_logger = PipelineLogger.create(pdf_file=Path(pdf_path).name)
    out_dir = run_logger.run_dir

    pdf_doc = extract_pdf(pdf_path)
    normalized = normalize_text(pdf_doc)

    # Stage 01: layout extraction (use production-enriched NormalizedLine fields)
    # NOTE: normalize_text() already yields enriched NormalizedLine objects (font_size, is_bold, centered, large_gap, etc).
    # `lines_to_log` converts them into the required 01_layout_lines.json schema.
    layout_payload = lines_to_log(normalized)
    run_logger.write_stage("layout_lines", layout_payload)

    # Stage 02: noise detection (never deletes lines)
    normalized, noise_log = mark_noise(normalized)
    run_logger.write_stage("noise_filter", noise_log)

    # Stage 03: candidate scoring (debug runner uses raw collector; enrich using stage-01 layout payload)
    candidates = collect_heading_candidates(normalized)

    # Build quick lookup from stage-01 layout payload for overlays/log enrichment
    layout_by_line_id = {it["line_id"]: it for it in layout_payload if isinstance(it, dict) and isinstance(it.get("line_id"), int)}

    candidate_log_items = []
    for c in candidates:
        lid = getattr(c, "start_line", None)
        layout = layout_by_line_id.get(lid) if isinstance(lid, int) else None

        # These are best-effort because debug collector may not compute scoring signals.
        # Debug runner uses HeadingCandidateCollector output which does not compute a numeric score.
        # For logging usefulness, compute a simple deterministic score_breakdown from layout signals.
        bold = bool(layout.get("is_bold")) if isinstance(layout, dict) else bool(getattr(c, "bold", False))
        centered = bool(layout.get("centered")) if isinstance(layout, dict) else bool(getattr(c, "centered", False))
        large_gap = bool(layout.get("large_gap")) if isinstance(layout, dict) else bool(getattr(c, "large_gap", False))
        large_font = bool(layout.get("large_font")) if isinstance(layout, dict) else False

        # Map to the stage-03 naming expected by your spec.
        signals: list[str] = []
        score_breakdown: dict[str, int] = {}

        if bold:
            signals.append("bold")
            score_breakdown["bold"] = 2
        if centered:
            signals.append("centered")
            score_breakdown["centered"] = 2
        if large_gap:
            signals.append("large_gap")
            score_breakdown["gap"] = 2
        if large_font:
            signals.append("large_font")
            score_breakdown["font"] = 1

        score = int(sum(score_breakdown.values()))

        # context preview is provided by HeadingCandidate.full_context_preview
        context_preview = getattr(c, "full_context_preview", None) or getattr(c, "context_preview", None)

        candidate_log_items.append(
            {
                "line_id": lid,
                "text": getattr(c, "text", ""),
                "page_number": (layout.get("page_number") if isinstance(layout, dict) else getattr(c, "page_number", None)),
                "score": score,
                "signals": signals,
                "selected": True,
                "score_breakdown": score_breakdown,
                "context_preview": context_preview,
                "bbox": (layout.get("bbox") if isinstance(layout, dict) else getattr(c, "bbox", None)),
                "font_size": (layout.get("font_size") if isinstance(layout, dict) else getattr(c, "font_size", None)),
                "bold": bold,
                "centered": centered,
                "large_gap": large_gap,
            }
        )
    run_logger.write_stage("candidate_scoring", candidate_log_items)

    # Stage 04: gemini heading validation (writes 04_gemini_heading_validation.json)
    validated = validate_headings(list(candidates), logger=run_logger)

    # Stage 05: gemini toc classification (writes 05_gemini_toc_classification.json)
    validated = classify_toc(validated, logger=run_logger)

    # Apply the same TOC resolver stage as the production pipeline.
    validated = resolve_toc_sections(validated, lines=normalized, logger=run_logger)

    fragments_result, fragments_log_items = build_fragments(normalized, validated)
    run_logger.write_stage("fragments", fragments_log_items)

    # assign_hierarchy expects List[FinalHeading]
    final_heads = [
        FinalHeading(
            id=h.id,
            text=h.text,
            level=1,
            fragment_id=getattr(fragments_result, "heading_to_fragment_id", {}).get(h.id),
        )
        for h in validated
        if getattr(h, "is_valid", None) is True and getattr(h, "is_toc", None) is False
    ]
    hierarchy = assign_hierarchy(final_heads, logger=run_logger)

    def _parse_line_id_from_heading_id(hid: Any) -> Optional[int]:
        if not isinstance(hid, str):
            return None
        if not hid.startswith("L"):
            return None
        try:
            return int(hid[1:].split(":", 1)[0])
        except Exception:
            return None

    # Backfill missing line_id/page_number from heading_id using stage-01 layout map
    # (debug runner uses simplified FinalHeading objects, so assign_hierarchy may not carry these fields)
    heading_id_to_line_id: dict[str, int] = {}
    for fh in final_heads:
        hid = getattr(fh, "id", None)
        lid = _parse_line_id_from_heading_id(hid)
        if isinstance(hid, str) and isinstance(lid, int):
            heading_id_to_line_id[hid] = lid

    hierarchy_log_items = []
    for h in hierarchy:
        hid = getattr(h, "id", None) or getattr(h, "heading_id", None)
        lid = getattr(h, "line_id", None)
        if not isinstance(lid, int) and isinstance(hid, str):
            lid = heading_id_to_line_id.get(hid) or _parse_line_id_from_heading_id(hid)

        page_number = getattr(h, "page_number", None)
        if not isinstance(page_number, int) and isinstance(lid, int):
            layout = layout_by_line_id.get(lid)
            if isinstance(layout, dict):
                page_number = layout.get("page_number")

        hierarchy_log_items.append(
            {
                "heading_id": hid,
                "text": getattr(h, "text", ""),
                "line_id": lid,
                "page_number": page_number,
                "assigned_level": getattr(h, "level", None),
                "parent_heading": getattr(h, "parent_heading", None),
                "reason": getattr(h, "reason", None),
                "signals_used": getattr(h, "signals_used", None),
                "model": getattr(h, "model", None),
                "latency_ms": getattr(h, "latency_ms", None),
            }
        )
    run_logger.write_stage("hierarchy", hierarchy_log_items)

    # Stage 09: final headings (post-clean)
    toc_out = clean_toc(hierarchy, fragments=fragments_result.fragments)
    final_items = []
    for h in toc_out:
        hid = getattr(h, "id", None) or getattr(h, "heading_id", None)

        lid = getattr(h, "line_id", None)
        if not isinstance(lid, int) and isinstance(hid, str):
            lid = heading_id_to_line_id.get(hid) or _parse_line_id_from_heading_id(hid)

        page_number = getattr(h, "page_number", None)
        if not isinstance(page_number, int) and isinstance(lid, int):
            layout = layout_by_line_id.get(lid)
            if isinstance(layout, dict):
                page_number = layout.get("page_number")

        final_items.append(
            {
                "heading_id": hid,
                "text": getattr(h, "text", ""),
                "level": getattr(h, "level", None),
                "parent_heading": getattr(h, "parent_heading", None),
                "fragment_id": getattr(h, "fragment_id", None),
                "page_number": page_number,
                "line_id": lid,
                "confidence": getattr(h, "confidence", None),
            }
        )
    run_logger.write_stage("final_headings", final_items)

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

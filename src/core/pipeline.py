"""
Phase 1 (restructure only):
This module is the production-facing pipeline entrypoint for the new clean deterministic core.

IMPORTANT:
- Imports from ONLY the new clean core modules.
- No imports from src/legacy.
- Logic is intentionally minimal/stubbed for now (behavior will be implemented in later phases).
"""

from .pdf_extractor import extract_pdf
from .text_normalizer import normalize_text
from .heading_candidate_collector import collect_heading_candidates
from .candidate_scorer import collect_candidates_scored
from .heading_validator import validate_headings
from .fragment_builder import build_fragments
from .hierarchy_assigner import assign_hierarchy
from .toc_cleaner import clean_toc
from .logging.pipeline_logger import PipelineLogger
from .layout_enrichment import lines_to_log
from .noise_filter import mark_noise
from .toc_classifier import classify_toc
from .toc_section_resolver import resolve_toc_sections
from pathlib import Path
from typing import Any, Optional


def _parse_line_id_from_heading_id(hid: Any) -> Optional[int]:
    if not isinstance(hid, str):
        return None
    if not hid.startswith("L"):
        return None
    try:
        return int(hid[1:].split(":", 1)[0])
    except Exception:
        return None


def run_pipeline(pdf_path: str, *, enable_logs: bool = False, persist_to_db: bool = False):
    """
    Orchestrates the clean core pipeline.

    Logging:
      - enable_logs=False (default): no log folder/files are created
      - enable_logs=True: writes exactly the 10 whitelisted stage logs under logs/run_<timestamp>/
    """
    logger = PipelineLogger.create(pdf_file=Path(pdf_path).name, enabled=enable_logs)

    pdf_doc = extract_pdf(pdf_path)
    lines = normalize_text(pdf_doc)

    # Stage 01: layout extraction
    layout_payload = lines_to_log(lines)
    logger.write_stage("layout_lines", layout_payload)
    layout_by_line_id = {it["line_id"]: it for it in layout_payload if isinstance(it, dict) and isinstance(it.get("line_id"), int)}

    # Stage 02: noise detection (never deletes lines)
    lines, noise_log = mark_noise(lines)
    logger.write_stage("noise_filter", noise_log)

    # Stage 03: candidate scoring (authoritative candidate selection)
    candidates, scoring_log = collect_candidates_scored(lines)
    logger.write_stage("candidate_scoring", scoring_log)

    headings = validate_headings(candidates, logger=logger)

    # Stage 05: Gemini TOC classification (no fragment text used)
    headings = classify_toc(headings, logger=logger)

    # Stage 06: remove TOC blocks (3+ consecutive is_toc==true and is_valid==false)
    headings = resolve_toc_sections(headings, lines=lines, logger=logger)

    fragments_result, fragments_log = build_fragments(lines, headings)
    logger.write_stage("fragments", fragments_log)

    # Stage 08: hierarchy assignment (Gemini)
    # Only use headings that survived validation + TOC filtering.
    from .models import FinalHeading

    fragment_map = getattr(fragments_result, "heading_to_fragment_id", {}) or {}
    final_heads = [
        FinalHeading(
            id=getattr(h, "id", None) or getattr(h, "heading_id", None),
            text=getattr(h, "text", ""),
            level=1,
            fragment_id=fragment_map.get(getattr(h, "id", None) or getattr(h, "heading_id", None)),
        )
        for h in headings
        if getattr(h, "is_valid", None) is True and getattr(h, "is_toc", None) is False
    ]

    hierarchy = assign_hierarchy(final_heads, logger=logger)

    # Backfill line_id/page_number from heading_id using stage-01 layout map
    heading_id_to_line_id: dict[str, int] = {}
    for fh in final_heads:
        hid = getattr(fh, "id", None)
        lid = _parse_line_id_from_heading_id(hid)
        if isinstance(hid, str) and isinstance(lid, int):
            heading_id_to_line_id[hid] = lid

    hierarchy_log_items = []
    for h in hierarchy:
        hid = getattr(h, "id", None)
        lid = _parse_line_id_from_heading_id(hid) if isinstance(hid, str) else None
        if isinstance(hid, str) and isinstance(lid, int):
            lid = heading_id_to_line_id.get(hid, lid)

        page_number = None
        if isinstance(lid, int):
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
                "model": getattr(h, "hierarchy_model", None),
                "latency_ms": getattr(h, "hierarchy_latency_ms", None),
            }
        )
    logger.write_stage("hierarchy", hierarchy_log_items)

    # Stage 09: final headings (post-clean)
    toc_out = clean_toc(hierarchy, fragments=fragments_result.fragments)
    final_headings_items = []
    for h in toc_out:
        hid = getattr(h, "id", None)

        lid = _parse_line_id_from_heading_id(hid) if isinstance(hid, str) else None
        if isinstance(hid, str) and isinstance(lid, int):
            lid = heading_id_to_line_id.get(hid, lid)

        page_number = None
        if isinstance(lid, int):
            layout = layout_by_line_id.get(lid)
            if isinstance(layout, dict):
                page_number = layout.get("page_number")

        final_headings_items.append(
            {
                "heading_id": hid,
                "text": getattr(h, "text", ""),
                "level": getattr(h, "level", None),
                "parent_heading": getattr(h, "parent_heading", None),
                "fragment_id": getattr(h, "fragment_id", None),
                "page_number": page_number,
                "line_id": lid,
                "confidence": getattr(h, "confidence", None),
                "reason": getattr(h, "reason", None),
                "signals_used": getattr(h, "signals_used", None),
                "model": getattr(h, "hierarchy_model", None),
                "latency_ms": getattr(h, "hierarchy_latency_ms", None),
            }
        )
    logger.write_stage("final_headings", final_headings_items)

    # Return production artifacts (DB/export can be built from this)
    from .models import PipelineResult

    result = PipelineResult(
        final_headings=toc_out,
        fragments=getattr(fragments_result, "fragments", []) or [],
        heading_to_fragment_id=getattr(fragments_result, "heading_to_fragment_id", {}) or {},
    )

    # Production persistence (DB becomes source-of-truth)
    if persist_to_db:
        from src.storage.knowledge_store import KnowledgeStore
        from src.storage.toc_repository import TocRepository

        # Current system uses output/knowledge_base.db as default.
        store = KnowledgeStore()
        repo = TocRepository(store)

        # For now, use pdf filename as book_id if caller didn't create a books row yet.
        # Prefer: real book_id from books table once ingestion flow is wired.
        book_id = Path(pdf_path).name

        repo.save_full_toc(
            book_id=book_id,
            final_headings=result.final_headings,
            fragments=result.fragments,
            heading_to_fragment_id=result.heading_to_fragment_id,
            clear_existing=True,
        )

    return result, (logger if enable_logs else None)

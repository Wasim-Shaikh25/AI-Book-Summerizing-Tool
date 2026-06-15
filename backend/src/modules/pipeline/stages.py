"""Pipeline stage plugins — each mutates PipelineContext in order."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from src.modules.ingestion.layout_enrichment import lines_to_log
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.ingestion.text_normalizer import normalize_text
from src.modules.pipeline.context import PipelineContext
from src.modules.pipeline.stage_15b import run_stage_15b_if_doubted
from src.modules.pipeline.stage_registry import (
    STAGE_RESOLVE_DOUBTED_REVALIDATION,
    STAGE_RESOLVE_DOUBTED_TOC,
)
from src.modules.structure.final_structuring.final_structuring_stage import run_final_structuring_stage
from src.modules.structure.candidate_scoring import collect_candidates_scored
from src.modules.structure.continuity_filter import apply_continuity_filter, parse_line_id_from_heading_id
from src.modules.structure.fragments import build_fragments
from src.modules.structure.heading_validity_gate import gate_heading_validity_candidates
from src.modules.structure.logging.pipeline_logger import PipelineLogger
from src.modules.structure.noise_filter import mark_noise
from src.modules.structure.toc_cleaning import clean_toc
from src.modules.structure.toc_repeat_detection import (
    book_metadata_from_first_toc_section,
    build_toc_sections_from_repeated_headings,
    detect_deterministic_toc,
)


def _final_headings_without_toc_and_metadata(
    final_headings_items: List[Dict[str, Any]],
    book_metadata_line_ids: Set[int],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in final_headings_items:
        if it.get("is_toc"):
            continue
        if it.get("in_toc_section"):
            continue
        lid = it.get("line_id")
        if isinstance(lid, int) and lid in book_metadata_line_ids:
            continue
        row = {k: v for k, v in it.items() if k not in ("is_toc", "in_toc_section")}
        out.append(row)
    return out


def stage_ingest_pdf(ctx: PipelineContext) -> None:
    enriched, title, visual = extract_pdf(ctx.pdf_path)
    ctx.lines = normalize_text((enriched, title))
    ctx.book_title = title
    ctx.visual_elements = visual


def stage_log_layout(ctx: PipelineContext) -> None:
    ctx.layout_payload = lines_to_log(ctx.lines)
    ctx.logger.write_stage("layout_lines", ctx.layout_payload)
    ctx.logger.write_stage("visual_elements", ctx.visual_elements)


def stage_filter_noise(ctx: PipelineContext) -> None:
    ctx.lines, noise_log = mark_noise(ctx.lines)
    ctx.logger.write_stage("noise_filter", noise_log)
    ctx.layout_by_line_id = {
        it["line_id"]: it
        for it in lines_to_log(ctx.lines)
        if isinstance(it, dict) and isinstance(it.get("line_id"), int)
    }


def stage_score_heading_candidates(ctx: PipelineContext) -> None:
    ctx.candidates, scoring_log = collect_candidates_scored(ctx.lines)
    ctx.logger.write_stage("candidate_scoring", scoring_log)


def stage_gate_heading_candidates(ctx: PipelineContext) -> None:
    ctx.candidates, gate_log = gate_heading_validity_candidates(ctx.candidates, lines=ctx.lines)
    ctx.dropped_heading_registry.extend_from_gate_log(gate_log)
    ctx.logger.write_stage("heading_validity_gate", gate_log)


def stage_filter_continuity(ctx: PipelineContext) -> None:
    ctx.headings, dropped = apply_continuity_filter(ctx.candidates, ctx.layout_by_line_id)
    ctx.dropped_heading_registry.extend_from_continuity_log(dropped)
    if dropped:
        ctx.logger.write_stage("continuity_filter", dropped)


def stage_build_fragments(ctx: PipelineContext) -> None:
    ctx.fragments_result, fragments_log = build_fragments(ctx.lines, ctx.headings)
    ctx.fragments_log = fragments_log
    ctx.logger.write_stage("fragments", fragments_log)
    heading_to_fragment_id = getattr(ctx.fragments_result, "heading_to_fragment_id", {}) or {}
    for h in ctx.headings:
        hid = getattr(h, "id", None)
        if isinstance(hid, str) and hid in heading_to_fragment_id:
            h.fragment_id = heading_to_fragment_id[hid]


def stage_clean_toc(ctx: PipelineContext) -> None:
    frags = getattr(ctx.fragments_result, "fragments", []) or []
    ctx.toc_out = clean_toc(list(ctx.headings), fragments=frags)


def stage_detect_toc(ctx: PipelineContext) -> None:
    ctx.toc_seed_ids, det_seed_log = detect_deterministic_toc(ctx.lines, ctx.toc_out)

    from src.modules.ingestion.pdf_outline import supplement_toc_from_pdf_outline

    ctx.toc_seed_ids, outline_log = supplement_toc_from_pdf_outline(
        ctx.pdf_path,
        ctx.lines,
        ctx.toc_out,
        ctx.toc_seed_ids,
    )

    for h in ctx.toc_out:
        lid = getattr(h, "line_id", None)
        h.is_toc = bool(isinstance(lid, int) and lid in ctx.toc_seed_ids)

    ctx.toc_section_line_ids, det_section_log = build_toc_sections_from_repeated_headings(ctx.lines, ctx.toc_out)

    from src.shared import config as _cfg

    if getattr(_cfg, "CONTENTS_REGION_DETECTION", True):
        from src.modules.structure.contents_region import detect_contents_regions

        region_ids, region_log = detect_contents_regions(ctx.lines)
        if region_ids:
            ctx.toc_section_line_ids = set(ctx.toc_section_line_ids) | region_ids
            det_section_log = list(det_section_log) + region_log

    for h in ctx.toc_out:
        lid = getattr(h, "line_id", None)
        h.in_toc_section = bool(isinstance(lid, int) and lid in ctx.toc_section_line_ids)

    ctx.det_toc_log_items = det_seed_log + outline_log + det_section_log

    ctx.book_metadata_line_ids, ctx.book_meta_log = book_metadata_from_first_toc_section(
        ctx.lines,
        det_section_log,
        headings=ctx.toc_out,
        fragments=getattr(ctx.fragments_result, "fragments", []) or [],
    )


def stage_flag_doubted_toc(ctx: PipelineContext) -> None:
    ctx.first_toc_page = 0
    for sr in ctx.det_toc_log_items:
        if sr.get("kind") == "toc_section_span":
            pg = int(sr.get("page_number_start") or 0)
            if pg and (ctx.first_toc_page == 0 or pg < ctx.first_toc_page):
                ctx.first_toc_page = pg

    if ctx.first_toc_page > 3:
        all_toc = ctx.toc_seed_ids | ctx.toc_section_line_ids
        ctx.doubted_toc_ids = ctx.book_metadata_line_ids & all_toc
        ctx.doubted_body_ids = ctx.book_metadata_line_ids - ctx.doubted_toc_ids
        ctx.book_metadata_line_ids = set()
        ctx.book_meta_log = []

    doubted_log = {
        "first_toc_page": ctx.first_toc_page,
        "is_doubted": ctx.first_toc_page > 3,
        "reason": (
            f"first_toc_found_on_page_{ctx.first_toc_page}"
            if ctx.first_toc_page > 3
            else "first_toc_within_page_3"
        ),
        "doubted_body_line_ids": sorted(ctx.doubted_body_ids),
        "doubted_toc_line_ids": sorted(ctx.doubted_toc_ids),
        "doubted_body_count": len(ctx.doubted_body_ids),
        "doubted_toc_count": len(ctx.doubted_toc_ids),
    }
    ctx.logger.write_stage("doubted_sections", [doubted_log])


def stage_resolve_doubted_toc(ctx: PipelineContext) -> None:
    if ctx.first_toc_page <= 3 or not (ctx.doubted_body_ids or ctx.doubted_toc_ids):
        ctx.logger.write_stage(STAGE_RESOLVE_DOUBTED_TOC, [])
        return
    segments, audits, metadata_ids = run_stage_15b_if_doubted(
        lines=ctx.lines,
        headings=ctx.toc_out,
        layout_by_line_id=ctx.layout_by_line_id,
        doubted_body_ids=ctx.doubted_body_ids,
        doubted_toc_ids=ctx.doubted_toc_ids,
        first_toc_page=ctx.first_toc_page,
        det_section_log=[r for r in ctx.det_toc_log_items if r.get("kind") == "toc_section_span"],
        toc_section_line_ids=ctx.toc_section_line_ids,
    )
    ctx.stage_15b_segments = segments
    ctx.stage_15b_audits = audits
    ctx.book_metadata_line_ids = metadata_ids
    if segments:
        ctx.logger.write_stage(STAGE_RESOLVE_DOUBTED_TOC, segments)
    if audits:
        ctx.logger.write_stage(STAGE_RESOLVE_DOUBTED_REVALIDATION, audits)


def stage_finalize_heading_list(ctx: PipelineContext) -> None:
    items: List[Dict[str, Any]] = []
    for h in ctx.toc_out:
        hid = getattr(h, "id", None)
        lid = parse_line_id_from_heading_id(hid) if isinstance(hid, str) else None
        page_number = None
        if isinstance(lid, int):
            layout = ctx.layout_by_line_id.get(lid)
            if isinstance(layout, dict):
                page_number = layout.get("page_number")
        items.append(
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
                "is_toc": bool(getattr(h, "is_toc", False)),
                "in_toc_section": bool(getattr(h, "in_toc_section", False)),
            }
        )
    ctx.final_headings_items = items
    final_headings_2 = _final_headings_without_toc_and_metadata(items, ctx.book_metadata_line_ids)
    ctx.final_headings_2_items = final_headings_2
    ctx.logger.write_stage("final_headings", items)
    ctx.logger.write_stage("final_headings_2", final_headings_2)
    ctx.logger.write_stage("deterministic_toc", ctx.det_toc_log_items)
    ctx.logger.write_stage("book_metadata", ctx.book_meta_log)


def stage_validate_early_titles(ctx: PipelineContext) -> None:
    """Stage s13 — rules-based title validation before 15a hierarchy and 15d section division."""
    from src import config as cfg
    from src.modules.structure.heading_title_validation import filter_validated_headings

    if not ctx.final_headings_2_items:
        return
    if not getattr(cfg, "TITLE_VALIDATION_ENABLED", True):
        ctx.logger.write_stage("heading_title_validation", [])
        return

    kept, dropped, stats = filter_validated_headings(
        ctx.final_headings_2_items,
        lines=ctx.lines,
        registry=ctx.dropped_heading_registry,
    )
    ctx.dropped_heading_registry.extend_from_title_validation_log(dropped)
    ctx.final_headings_2_items = kept
    ctx.logger.write_stage("heading_title_validation", dropped)
    ctx.logger.write_stage("validated_headings", kept)


def stage_compute_document_profile(ctx: PipelineContext) -> None:
    """Measure document shape and persist tuning knobs for downstream stages."""
    from src.modules.ingestion.document_profile import compute_document_profile
    from src.modules.pipeline.stage_registry import STAGE_DOCUMENT_PROFILE

    profile = compute_document_profile(ctx.lines, ctx.final_headings_2_items)
    ctx.document_profile = profile
    ctx.logger.write_stage_payload(STAGE_DOCUMENT_PROFILE, profile.to_dict())


def stage_build_book_structure(ctx: PipelineContext) -> None:
    if not ctx.final_headings_2_items:
        return
    run_final_structuring_stage(
        logger=ctx.logger,
        lines=ctx.lines,
        book_title=ctx.book_title or ctx.pdf_name,
        final_headings_2=ctx.final_headings_2_items,
        fragments_log=ctx.fragments_log,
        metadata_line_ids=set(ctx.book_metadata_line_ids),
        toc_seed_ids=set(ctx.toc_seed_ids),
        first_toc_page=ctx.first_toc_page,
        is_doubted=ctx.first_toc_page > 3,
        doubted_segments=ctx.stage_15b_segments or None,
        dropped_registry=ctx.dropped_heading_registry,
        document_profile=ctx.document_profile,
    )


# Deprecated aliases (pre-2026-06 rename) — keep for external imports and old docs.
stage_extract = stage_ingest_pdf
stage_layout_log = stage_log_layout
stage_noise = stage_filter_noise
stage_candidates = stage_score_heading_candidates
stage_heading_gate = stage_gate_heading_candidates
stage_continuity = stage_filter_continuity
stage_fragments = stage_build_fragments
stage_toc_clean = stage_clean_toc
stage_deterministic_toc = stage_detect_toc
stage_doubted_sections = stage_flag_doubted_toc
stage_15b_resolver = stage_resolve_doubted_toc
stage_finalize_headings = stage_finalize_heading_list
stage_heading_title_validation = stage_validate_early_titles
stage_final_structuring = stage_build_book_structure

from src.modules.pipeline.stage_registry import get_pipeline_stages

STAGES = get_pipeline_stages()

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


def run_pipeline(pdf_path: str):
    """
    Orchestrates the clean core pipeline.
    """
    logger = PipelineLogger.create(pdf_file=Path(pdf_path).name)

    pdf_doc = extract_pdf(pdf_path)
    lines = normalize_text(pdf_doc)

    # Stage 01: layout extraction
    logger.write_stage("layout_lines", lines_to_log(lines))

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

    # Stage 08 / 09 are not yet fully wired in Phase-1 pipeline.
    # Logging should not change any logic/decisions, but we can still log what we have.
    logger.write_stage("hierarchy", [])

    # Stage 09: final headings (best available at this phase = post-TOC-cleaned headings list)
    final_headings_items = []
    for h in headings:
        final_headings_items.append(
            {
                "heading_id": getattr(h, "heading_id", None) or getattr(h, "id", None),
                "text": getattr(h, "text", ""),
                "level": getattr(h, "level", None),
                "parent_heading": getattr(h, "parent_heading", None),
                "fragment_id": getattr(fragments_result, "heading_to_fragment_id", {}).get(
                    getattr(h, "heading_id", None) or getattr(h, "id", None)
                ),
                "page_number": getattr(h, "page_number", None),
                "line_id": getattr(h, "line_id", None),
                "confidence": getattr(h, "confidence", None),
            }
        )
    logger.write_stage("final_headings", final_headings_items)

    return fragments_result

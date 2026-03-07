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
from .fragment_builder_v2 import build_fragments_v2
from .hierarchy_assigner import assign_hierarchy
from .toc_cleaner import clean_toc
from .logging.pipeline_logger import PipelineLogger
from .layout_enrichment import lines_to_log
from .noise_filter import mark_noise
from .toc_classifier import classify_toc
from .toc_section_resolver import resolve_toc_sections


def run_pipeline(pdf_path: str):
    """
    Orchestrates the clean core pipeline.
    """
    logger = PipelineLogger.create()

    pdf_doc = extract_pdf(pdf_path)
    lines = normalize_text(pdf_doc)

    # Stage 01 (temporary): log enriched lines. Full stage wiring will come next.
    logger.write_json("01_layout_lines.json", lines_to_log(lines))

    # Stage 02: noise detection (never deletes lines)
    lines, noise_log = mark_noise(lines)
    logger.write_json("02_noise_filter.json", noise_log)

    # Stage 03: candidate scoring (authoritative candidate selection)
    candidates, scoring_log = collect_candidates_scored(lines)
    logger.write_json("03_candidate_scoring.json", scoring_log)

    headings = validate_headings(candidates, logger=logger)

    # Stage 05: Gemini TOC classification (no fragment text used)
    headings = classify_toc(headings, logger=logger)

    # Stage 06: remove TOC blocks (3+ consecutive is_toc==true and is_valid==false)
    headings = resolve_toc_sections(headings, lines=lines, logger=logger)

    fragments_result_v2, fragments_log = build_fragments_v2(lines, headings)
    logger.write_json("07_fragments.json", fragments_log)

    # NOTE: hierarchy_assigner expects FinalHeading entries, but the full Phase-2+
    # pipeline will construct those after TOC resolver + fragment assignment.
    # For now, return the intermediate so we can validate layout/noise/candidate stages safely.
    return fragments_result_v2

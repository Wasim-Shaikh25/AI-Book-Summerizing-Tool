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
from .heading_validator import validate_headings
from .fragment_builder import build_fragments
from .hierarchy_assigner import assign_hierarchy
from .toc_cleaner import clean_toc


def run_pipeline(pdf_path: str):
    """
    Orchestrates the Phase-1 clean core pipeline.

    NOTE: Placeholder wiring only; do not treat as final behavior.
    """
    pdf_doc = extract_pdf(pdf_path)
    text = normalize_text(pdf_doc)
    candidates = collect_heading_candidates(text)
    headings = validate_headings(candidates)
    fragments = build_fragments(text, headings)
    hierarchy = assign_hierarchy(fragments)
    toc = clean_toc(hierarchy)
    return toc

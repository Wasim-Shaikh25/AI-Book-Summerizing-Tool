import json
import os
from pathlib import Path
from typing import Dict

import pytest

from src.core.heading_candidate_collector import collect_heading_candidates
from src.core.heading_validator import validate_headings
from src.core.fragment_builder import build_fragments
from src.core.hierarchy_assigner import assign_hierarchy
from src.core.models import FinalHeading, NormalizedLine
from src.core.toc_cleaner import clean_toc
from src.core.pdf_extractor import extract_pdf
from src.core.text_normalizer import normalize_text


def _ensure_logs_dir() -> Path:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _pick_pdf() -> Path:
    """
    Loads a PDF from: reference/<your_pdf_filename>.pdf

    We pick the first *.pdf found in ./reference/ for deterministic CI behavior.
    """
    ref_dir = Path("reference")
    if not ref_dir.exists():
        raise FileNotFoundError("Expected ./reference/ directory (reference/<your_pdf_filename>.pdf)")

    pdfs = sorted(ref_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError("No PDF found in ./reference/ (expected reference/<your_pdf_filename>.pdf)")

    return pdfs[0]


@pytest.mark.integration
def test_real_pdf_with_gemini_full_pipeline():
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set; skipping real Gemini integration test")

    pdf_path = _pick_pdf()

    # 1) PDF extraction
    pdf_doc = extract_pdf(str(pdf_path))

    # 2) Text normalization
    # normalize_text may return either List[NormalizedLine] or raw text depending on phase;
    # for this integration test, we normalize into List[NormalizedLine] deterministically.
    normalized = normalize_text(pdf_doc)

    if isinstance(normalized, str):
        # Fallback: treat as raw text split into lines (should be removed once normalizer returns models)
        normalized_lines = [
            NormalizedLine(id=i, text=line, page_number=None)
            for i, line in enumerate(normalized.splitlines())
        ]
    else:
        normalized_lines = list(normalized)

    total_lines = len(normalized_lines)
    total_text_length_before = len("\n".join([l.text for l in normalized_lines]))

    # 3) Heading candidate detection (universal)
    candidates = collect_heading_candidates(normalized_lines)
    assert len(candidates) >= 1, "Safety: expected at least 1 heading candidate"

    # 4) Gemini filtering / validation
    validated = validate_headings(list(candidates))

    # Fail test if any heading remains is_valid=None
    if any(c.is_valid is None for c in validated):
        raise AssertionError("Gemini validation incomplete: some candidates remain is_valid=None")

    valid_headings = [c for c in validated if c.is_valid is True]
    assert len(valid_headings) >= 1, "Safety: expected at least 1 valid heading after filtering"

    # 5) Fragment building + merge safety (zero loss)
    frag_result = build_fragments(normalized_lines, validated)

    fragments = frag_result.fragments
    assert len(fragments) >= 1, "Safety: expected fragments to be built"

    # No fragment should have empty text
    empties = [f.fragment_id for f in fragments if f.text == ""]
    assert not empties, f"Safety: fragments with empty text found: {empties}"

    total_text_length_after = sum(len(f.text) for f in fragments)

    # Total fragment text length equals total normalized text length (no loss)
    assert (
        total_text_length_after == total_text_length_before
    ), f"Text loss detected: before={total_text_length_before} after={total_text_length_after}"

    # No duplicate fragment_ids
    fragment_ids = [f.fragment_id for f in fragments]
    assert len(fragment_ids) == len(set(fragment_ids)), "Duplicate fragment_ids detected"

    # 6) Convert to FinalHeading (minimal deterministic conversion for this integration test)
    # Every valid heading must have fragment_id assigned via frag_result mapping.
    final_headings = []
    for h in valid_headings:
        frag_id = frag_result.heading_to_fragment_id.get(h.id)
        assert frag_id is not None, f"Missing fragment mapping for valid heading id={h.id}"
        final_headings.append(
            FinalHeading(
                id=h.id,
                text=h.text,
                level=None,
                fragment_id=frag_id,
            )
        )

    # 7) Hierarchy assignment (Gemini)
    hierarchical = assign_hierarchy(final_headings)

    # Fail test if Gemini response malformed (no levels assigned at all)
    if all(h.level is None for h in hierarchical):
        raise AssertionError("Gemini hierarchy response malformed or empty: all levels are None")

    levels_distribution: Dict[str, int] = {}
    for h in hierarchical:
        if h.level is None:
            continue
        levels_distribution[str(h.level)] = levels_distribution.get(str(h.level), 0) + 1

    # 8) TOC cleaning
    cleaned = clean_toc(hierarchical, fragments=fragments)

    # Print structured summaries
    print("\n=== INTEGRATION SUMMARY ===")
    print(f"PDF: {pdf_path}")
    print(f"Total normalized lines: {total_lines}")
    print(f"Total heading candidates detected: {len(candidates)}")
    print(f"Total headings after Gemini filtering: {len(valid_headings)}")
    print(f"Total fragments after merge: {len(fragments)}")
    print(f"Total final headings after TOC cleaning: {len(cleaned)}")
    print(f"Hierarchy level distribution: {levels_distribution}")
    print("===========================\n")

    # Write integration summary to logs
    logs_dir = _ensure_logs_dir()
    summary = {
        "total_lines": total_lines,
        "candidates_detected": len(candidates),
        "valid_headings": len(valid_headings),
        "fragments_count": len(fragments),
        "total_text_length_before": total_text_length_before,
        "total_text_length_after": total_text_length_after,
        "levels_distribution": levels_distribution,
    }
    (logs_dir / "integration_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

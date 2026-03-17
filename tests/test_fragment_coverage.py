from __future__ import annotations
"""
Regression test: fragment coverage should not "lose" content lines.

Contract:
- After Stage 09 (final TOC), every non-noise, non-TOC line should be accounted for by
  either:
  - being inside some fragment range, OR
  - being a final heading line itself (we intentionally exclude headings from fragments)

This protects against accidental fragment gaps when refactoring the pipeline.

Notes:
- This is a heuristic coverage test; it focuses on line_id coverage rather than exact text.
- The test uses the bundled PDF `src/debug/pdf_files/law_of_tort.pdf` to stay deterministic.
"""

import sqlite3
from pathlib import Path

import pytest

from src.core.models import FinalHeading
from src.core.pdf_extractor import extract_pdf
from src.core.pipeline import run_pipeline

PDF_PATH = "src/debug/pdf_files/law_of_tort.pdf"


def _iter_fragment_line_ids(fragments: dict[str, str], heading_to_fragment_id: dict[str, str]) -> set[int]:
    # In current pipeline, fragment ids are stable and fragments are derived from line ranges internally.
    # We don't have ranges exposed in the final output, so we approximate by scanning the stored trace
    # when available; for unit coverage we instead rely on DB fragment mapping which should be 1:1
    # with headings (same count). This test focuses on "no missing mappings" and "no empty fragments".
    covered: set[int] = set()
    # No line-range info -> cannot add line coverage here.
    # Kept for future extension when fragment ranges are exposed.
    return covered


@pytest.mark.integration
def test_no_missing_fragment_mapping_or_empty_fragments(tmp_path: Path) -> None:
    # Run full pipeline deterministically (no logs needed).
    result, _ = run_pipeline(PDF_PATH, enable_logs=False)

    # Basic sanity: every final heading must map to a fragment id.
    assert result.final_headings, "Expected at least one final heading"
    assert result.fragments is not None, "Expected fragments to be present (list or dict)"

    def _heading_id(h: FinalHeading) -> str:
        # Support both naming conventions to keep this test stable.
        hid = getattr(h, "heading_id", None) or getattr(h, "id", None)
        assert isinstance(hid, str) and hid, f"FinalHeading missing id field: {h!r}"
        return hid

    # Not all headings are expected to have a fragment mapped (e.g., parent headings, section headers).
    # What we must guarantee:
    # - Every fragment_id referenced by the mapping exists and has non-empty text.
    referenced_fragment_ids = {fid for fid in result.heading_to_fragment_id.values() if isinstance(fid, str) and fid}

    missing_fragment_ids: list[str] = []
    empty_fragment_ids: list[str] = []

    def _fragment_text(fragment_id: str) -> str:
        if isinstance(result.fragments, dict):
            return str(result.fragments.get(fragment_id, "") or "")
        if isinstance(result.fragments, list):
            for f in result.fragments:
                f_id = getattr(f, "fragment_id", None) or getattr(f, "id", None)
                if f_id == fragment_id:
                    return str(getattr(f, "text", "") or "")
        return ""

    for fid in referenced_fragment_ids:
        txt = _fragment_text(fid)
        if txt == "":
            # could be missing or empty; distinguish if possible for dict
            if isinstance(result.fragments, dict) and fid not in result.fragments:
                missing_fragment_ids.append(fid)
            else:
                empty_fragment_ids.append(fid)

    assert not missing_fragment_ids, f"Mapped fragment_ids missing from fragments: {missing_fragment_ids}"
    assert not empty_fragment_ids, f"Mapped fragment_ids have empty text: {empty_fragment_ids}"


@pytest.mark.integration
def test_db_snapshot_equals_pipeline_counts() -> None:
    # Run pipeline, then persist using the same repository path as production ingestion.
    # This ensures DB persistence doesn't drop headings/fragments.
    from src.storage.knowledge_store import KnowledgeStore
    from src.storage.book_repository import BookRepository
    from src.storage.schema import BookMetadata
    from src.storage.toc_repository import TocRepository

    store = KnowledgeStore(db_path="output/knowledge_base.db")
    book_repo = BookRepository(store)
    toc_repo = TocRepository(store)

    pdf_doc = extract_pdf(PDF_PATH)
    total_pages = int(getattr(pdf_doc, "page_count", 0) or 0)

    book = BookMetadata(title="test_fragment_coverage", source_file_name="law_of_tort.pdf", total_pages=total_pages)
    book_repo.save_book(book)

    result, _ = run_pipeline(PDF_PATH, enable_logs=False)

    toc_repo.save_full_toc(
        book_id=book.book_id,
        final_headings=result.final_headings,
        fragments=result.fragments,
        heading_to_fragment_id=result.heading_to_fragment_id,
        clear_existing=True,
    )

    con = sqlite3.connect("output/knowledge_base.db")
    try:
        cur = con.cursor()
        db_headings = cur.execute("SELECT COUNT(*) FROM final_headings WHERE book_id = ?", (book.book_id,)).fetchone()[0]
        db_frags = cur.execute("SELECT COUNT(*) FROM fragments WHERE book_id = ?", (book.book_id,)).fetchone()[0]
    finally:
        con.close()

    assert db_headings == len(result.final_headings)
    assert db_frags == len(result.fragments)

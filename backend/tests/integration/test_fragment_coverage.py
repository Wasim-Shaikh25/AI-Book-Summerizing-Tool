from __future__ import annotations

"""
Regression: fragment / DB persistence invariants for the bundled sample PDF.
"""

import sqlite3
from pathlib import Path

import pytest

from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.pipeline import run_pipeline
from src.modules.storage.book_repository import BookRepository
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.schema import BookMetadata
from src.modules.storage.toc_repository import TocRepository

from tests.conftest import sample_pdf_path


def _max_page_from_lines(pdf_path: str) -> int:
    lines, _book_title, _visual = extract_pdf(pdf_path)
    pages = {getattr(ln, "page_number", None) for ln in lines}
    pages.discard(None)
    return max(pages) if pages else 0


@pytest.mark.integration
def test_no_missing_fragment_mapping_or_empty_fragments() -> None:
    result, _ = run_pipeline(sample_pdf_path(), enable_logs=False)

    assert result.final_headings, "Expected at least one final heading"
    assert result.fragments is not None, "Expected fragments to be present (list or dict)"

    referenced_fragment_ids = {fid for fid in result.heading_to_fragment_id.values() if isinstance(fid, str) and fid}

    def _has_fragment(fragment_id: str) -> bool:
        if isinstance(result.fragments, dict):
            return fragment_id in result.fragments
        if isinstance(result.fragments, list):
            for f in result.fragments:
                f_id = getattr(f, "fragment_id", None) or getattr(f, "id", None)
                if f_id == fragment_id:
                    return True
        return False

    missing = [fid for fid in referenced_fragment_ids if not _has_fragment(fid)]
    assert not missing, f"heading_to_fragment_id references unknown fragment ids: {missing[:20]}"


@pytest.mark.integration
def test_db_snapshot_equals_pipeline_counts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_kb.db")
    store = KnowledgeStore(db_path=db_path)
    book_repo = BookRepository(store)
    toc_repo = TocRepository(store)

    pdf = sample_pdf_path()
    total_pages = _max_page_from_lines(pdf)

    book = BookMetadata(
        title="test_fragment_coverage",
        source_file_name=Path(pdf).name,
        total_pages=total_pages,
    )
    book_repo.save_book(book)

    result, _ = run_pipeline(pdf, enable_logs=False)

    toc_repo.save_full_toc(
        book_id=book.book_id,
        final_headings=result.final_headings,
        fragments=result.fragments,
        heading_to_fragment_id=result.heading_to_fragment_id,
        clear_existing=True,
    )

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        db_headings = cur.execute(
            "SELECT COUNT(*) FROM final_headings WHERE book_id = ?", (book.book_id,)
        ).fetchone()[0]
        db_frags = cur.execute(
            "SELECT COUNT(*) FROM fragments WHERE book_id = ?", (book.book_id,)
        ).fetchone()[0]
    finally:
        con.close()

    assert db_headings == len(result.final_headings)
    assert db_frags == len(result.fragments)


@pytest.mark.integration
def test_run_pipeline_returns_nonempty_artifacts() -> None:
    """Smoke: deterministic pipeline produces headings and fragments."""
    result, _ = run_pipeline(sample_pdf_path(), enable_logs=False)
    assert len(result.final_headings) >= 1
    assert len(result.fragments) >= 1
    assert isinstance(result.heading_to_fragment_id, dict)

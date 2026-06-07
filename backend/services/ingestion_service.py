"""PDF ingestion service wrapping existing pipeline."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from src import config
from src.modules.generation.toc_sections import load_rewrite_sections
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.pipeline import run_pipeline
from src.modules.rag.service import RagService
from src.modules.storage.book_repository import BookRepository
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.schema import BookMetadata
from src.modules.storage.toc_repository import TocRepository

from storage.user_repository import UserBookRepository

logger = logging.getLogger(__name__)


def _upload_dir(user_id: str) -> Path:
    base = Path(getattr(config, "OUTPUT_FOLDER", "output"))
    return base / "uploads" / user_id


class IngestionService:
    def __init__(self) -> None:
        self.store = KnowledgeStore()
        self.book_repo = BookRepository(self.store)
        self.toc_repo = TocRepository(self.store)
        self.user_books = UserBookRepository()

    def ingest_upload(
        self,
        user_id: str,
        upload_path: str,
        original_name: str,
        *,
        skip_rag: bool | None = None,
        on_progress=None,
    ) -> dict[str, Any]:
        def progress(status: str, message: str) -> None:
            if on_progress:
                on_progress(status, message)

        upload_dir = _upload_dir(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / original_name
        if str(upload_path) != str(dest):
            shutil.copy2(upload_path, dest)
        file_path = str(dest)

        progress("extracting", "Reading PDF and extracting text...")
        lines, book_title, _ = extract_pdf(file_path)
        pages = {ln.page_number for ln in lines if getattr(ln, "page_number", None) is not None}
        total_pages = max(pages) if pages else 0
        title = book_title or os.path.splitext(original_name)[0]

        book = BookMetadata(
            title=title,
            source_file_name=original_name,
            total_pages=total_pages,
        )
        self.book_repo.save_book(book)

        progress("pipeline", "Analyzing structure (headings, TOC, sections)...")
        result, pipeline_logger = run_pipeline(file_path, enable_logs=True, persist_to_db=False)
        log_dir = str(pipeline_logger.run_dir) if pipeline_logger else None

        progress("saving", "Saving book structure to database...")
        self.toc_repo.save_full_toc(
            book_id=book.book_id,
            final_headings=result.final_headings,
            fragments=result.fragments,
            heading_to_fragment_id=result.heading_to_fragment_id,
            clear_existing=True,
        )

        self.user_books.link(user_id, book.book_id, file_path, log_dir)

        if skip_rag is None:
            skip_rag = os.getenv("UPLOAD_SKIP_RAG", "true").strip().lower() in {"1", "true", "yes", "on"}

        rag_chunks = 0
        if not skip_rag and getattr(config, "RAG_ENABLED", True) and log_dir:
            progress("rag", "Building search index (first time may take a few minutes)...")
            try:
                log_path = Path(log_dir)
                h15f = log_path / "15f_heading_cleanup.json"
                h15e = log_path / "15e_chapter_hierarchy.json"
                hierarchy_path = h15f if h15f.exists() else h15e
                sections = load_rewrite_sections(
                    self.store,
                    book_id=book.book_id,
                    pdf_path=file_path,
                    ultimate_sections_path=log_path / "15d_ultimate_sections.json",
                    chapter_hierarchy_path=hierarchy_path if hierarchy_path.exists() else None,
                    lines=lines,
                    prefer_15e=True,
                    prefer_15d=True,
                )
                if sections:
                    idx = RagService(self.store).ensure_index(book_id=book.book_id, sections=sections)
                    rag_chunks = idx.chunk_count
            except Exception as exc:
                logger.warning("RAG index build skipped: %s", exc)
        progress("done", "Book is ready for chat.")
        return {
            "book_id": book.book_id,
            "title": title,
            "total_pages": total_pages,
            "final_headings": len(result.final_headings),
            "fragments": len(result.fragments),
            "log_dir": log_dir,
            "rag_chunks": rag_chunks,
        }

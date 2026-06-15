"""PDF ingestion service wrapping existing pipeline."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Callable

from src import config
from src.shared.paths import to_project_relative_path
from src.modules.generation.toc_sections import load_rewrite_sections
from src.modules.ingestion.profile import ingestion_profile_context, upload_skip_rag_default
from src.modules.pipeline.stage_registry import (
    STAGE_15D,
    STAGE_15E,
    STAGE_15F,
    resolve_existing_artifact,
)
from src.modules.pipeline import run_pipeline
from src.modules.rag.service import RagService
from src.modules.storage.book_repository import BookRepository
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.schema import BookMetadata
from src.modules.storage.toc_repository import TocRepository

from storage.user_repository import UserBookRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int | None], None]


def _upload_dir(user_id: str) -> Path:
    return Path(getattr(config, "UPLOADS_FOLDER", Path(config.OUTPUT_FOLDER) / "uploads")) / user_id


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
        profile: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        def progress(stage: str, message: str, percent: int | None = None) -> None:
            if on_progress:
                on_progress(stage, message, percent)

        upload_dir = _upload_dir(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / original_name
        if str(upload_path) != str(dest):
            shutil.copy2(upload_path, dest)
        file_path = str(dest)

        with ingestion_profile_context(profile):
            if skip_rag is None:
                skip_rag = upload_skip_rag_default()

            def pipeline_progress(stage_id: str, message: str, percent: int) -> None:
                progress(stage_id, message, percent)

            progress("pipeline", "Starting structure extraction...", 0)
            result, pipeline_logger = run_pipeline(
                file_path,
                enable_logs=True,
                persist_to_db=False,
                on_progress=pipeline_progress,
            )
            log_dir = str(pipeline_logger.run_dir) if pipeline_logger else None

            title = result.book_title or Path(original_name).stem
            total_pages = result.total_pages

            book = BookMetadata(
                title=title,
                source_file_name=original_name,
                total_pages=total_pages,
            )
            self.book_repo.save_book(book)

            progress("saving", "Saving book structure to database...", 92)
            self.toc_repo.save_full_toc(
                book_id=book.book_id,
                final_headings=result.final_headings,
                fragments=result.fragments,
                heading_to_fragment_id=result.heading_to_fragment_id,
                clear_existing=True,
            )

            self.user_books.link(
            user_id,
            book.book_id,
            to_project_relative_path(file_path),
            to_project_relative_path(log_dir) if log_dir else None,
        )

            rag_chunks = 0
            if not skip_rag and getattr(config, "RAG_ENABLED", True) and log_dir:
                progress("rag", "Building search index (first time may take a few minutes)...", 95)
                try:
                    log_path = Path(log_dir)
                    h15f = resolve_existing_artifact(log_path, STAGE_15F)
                    h15e = resolve_existing_artifact(log_path, STAGE_15E)
                    hierarchy_path = h15f or h15e
                    s15d = resolve_existing_artifact(log_path, STAGE_15D)
                    sections = load_rewrite_sections(
                        self.store,
                        book_id=book.book_id,
                        pdf_path=file_path,
                        ultimate_sections_path=s15d,
                        chapter_hierarchy_path=hierarchy_path,
                        lines=result.lines,
                        prefer_15e=True,
                        prefer_15d=True,
                    )
                    if sections:
                        idx = RagService(self.store).ensure_index(book_id=book.book_id, sections=sections)
                        rag_chunks = idx.chunk_count
                except Exception as exc:
                    logger.warning("RAG index build skipped: %s", exc)

        progress("done", "Book is ready for chat.", 100)
        return {
            "book_id": book.book_id,
            "title": title,
            "total_pages": total_pages,
            "final_headings": len(result.final_headings),
            "fragments": len(result.fragments),
            "log_dir": log_dir,
            "rag_chunks": rag_chunks,
        }

"""
Production pipeline orchestrator (MESO plugin shell).

Each stage lives in ``stages.py`` and mutates ``PipelineContext``.
"""

from __future__ import annotations

from pathlib import Path

from src.shared.models import PipelineResult
from src.modules.pipeline.context import PipelineContext
from src.modules.pipeline.stage_registry import STAGE_LOG_FILES, stage_progress_for
from src.modules.pipeline.stages import STAGES
from src.modules.structure.logging.pipeline_logger import PipelineLogger


def _total_pages(lines) -> int:
    pages = {ln.page_number for ln in lines if getattr(ln, "page_number", None) is not None}
    return max(pages) if pages else 0


def run_pipeline(
    pdf_path: str,
    *,
    enable_logs: bool = False,
    persist_to_db: bool = False,
    on_progress=None,
):
    logger = PipelineLogger.create(pdf_file=Path(pdf_path).name, enabled=enable_logs)
    ctx = PipelineContext(
        pdf_path=pdf_path,
        enable_logs=enable_logs,
        persist_to_db=persist_to_db,
        logger=logger,
        on_progress=on_progress,
    )

    for stage in STAGES:
        progress = stage_progress_for(stage.__name__)
        if progress and ctx.on_progress:
            stage_id, message, percent = progress
            ctx.on_progress(stage_id, message, percent)
        stage(ctx)

    result = PipelineResult(
        final_headings=ctx.toc_out,
        fragments=getattr(ctx.fragments_result, "fragments", []) or [],
        heading_to_fragment_id=getattr(ctx.fragments_result, "heading_to_fragment_id", {}) or {},
        lines=list(ctx.lines),
        book_title=ctx.book_title or Path(ctx.pdf_path).stem,
        total_pages=_total_pages(ctx.lines),
    )

    if persist_to_db:
        _persist(ctx, result)

    return result, (logger if enable_logs else None)


def _persist(ctx: PipelineContext, result: PipelineResult) -> None:
    from src.modules.storage.book_repository import BookRepository
    from src.modules.storage.knowledge_store import KnowledgeStore
    from src.modules.storage.schema import BookMetadata
    from src.modules.storage.toc_repository import TocRepository

    store = KnowledgeStore()
    book_repo = BookRepository(store)
    repo = TocRepository(store)

    book = BookMetadata(
        title=result.book_title or Path(ctx.pdf_path).stem,
        subject="unknown",
        source_file_name=Path(ctx.pdf_path).name,
        total_pages=result.total_pages,
    )
    book_repo.save_book(book)
    repo.save_full_toc(
        book_id=book.book_id,
        final_headings=result.final_headings,
        fragments=result.fragments,
        heading_to_fragment_id=result.heading_to_fragment_id,
        clear_existing=True,
    )

    # Save sections for RAG indexing
    _save_sections_for_rag(store, book.book_id, result.fragments, result.final_headings)

    if ctx.enable_logs and ctx.logger is not None:
        for stage_name, filename in STAGE_LOG_FILES.items():
            path = ctx.logger.run_dir / filename
            if not path.exists():
                continue
            store.save_pipeline_artifact(
                book_id=book.book_id,
                stage_name=stage_name,
                filename=filename,
                payload=path.read_text(encoding="utf-8"),
                run_id=getattr(ctx.logger, "run_id", None),
            )


def _save_sections_for_rag(store: KnowledgeStore, book_id: str, fragments: list, headings: list) -> None:
    """Save sections from fragments for RAG indexing."""
    conn = store.get_connection()
    try:
        cur = conn.cursor()

        # Create sections table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sections (
                section_id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                title TEXT,
                content TEXT,
                page_start INTEGER,
                page_end INTEGER,
                FOREIGN KEY (book_id) REFERENCES books (book_id)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sections_book ON sections (book_id)")

        # Clear existing sections for this book
        cur.execute("DELETE FROM sections WHERE book_id = ?", (book_id,))

        # Create sections from fragments
        import uuid
        for i, fragment in enumerate(fragments):
            if hasattr(fragment, 'heading') and hasattr(fragment, 'content'):
                section_id = str(uuid.uuid4())
                title = getattr(fragment, 'heading', f'Section {i+1}')
                content = getattr(fragment, 'content', '')
                page_start = getattr(fragment, 'page_start', None)
                page_end = getattr(fragment, 'page_end', None)

                cur.execute("""
                    INSERT INTO sections (section_id, book_id, title, content, page_start, page_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (section_id, book_id, title, content, page_start, page_end))

        conn.commit()
    finally:
        conn.close()

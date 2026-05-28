"""
Production pipeline orchestrator (MESO plugin shell).

Each stage lives in ``stages.py`` and mutates ``PipelineContext``.
"""

from __future__ import annotations

from pathlib import Path

from src.shared.models import PipelineResult
from src.modules.pipeline.context import PipelineContext
from src.modules.pipeline.stages import STAGES
from src.modules.structure.logging.pipeline_logger import PipelineLogger


def run_pipeline(pdf_path: str, *, enable_logs: bool = False, persist_to_db: bool = False):
    logger = PipelineLogger.create(pdf_file=Path(pdf_path).name, enabled=enable_logs)
    ctx = PipelineContext(
        pdf_path=pdf_path,
        enable_logs=enable_logs,
        persist_to_db=persist_to_db,
        logger=logger,
    )

    for stage in STAGES:
        stage(ctx)

    result = PipelineResult(
        final_headings=ctx.toc_out,
        fragments=getattr(ctx.fragments_result, "fragments", []) or [],
        heading_to_fragment_id=getattr(ctx.fragments_result, "heading_to_fragment_id", {}) or {},
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
        title=Path(ctx.pdf_path).stem,
        subject="unknown",
        source_file_name=Path(ctx.pdf_path).name,
        total_pages=0,
    )
    book_repo.save_book(book)
    repo.save_full_toc(
        book_id=book.book_id,
        final_headings=result.final_headings,
        fragments=result.fragments,
        heading_to_fragment_id=result.heading_to_fragment_id,
        clear_existing=True,
    )

    if ctx.enable_logs and ctx.logger is not None:
        stage_files = {
            "layout_lines": "01_layout_lines.json",
            "noise_filter": "02_noise_filter.json",
            "candidate_scoring": "03_candidate_scoring.json",
            "heading_validity_gate": "03b_heading_validity_gate.json",
            "fragments": "07_fragments.json",
            "continuity_filter": "08b_continuity_filter.json",
            "final_headings": "09_final_headings.json",
            "deterministic_toc": "10_deterministic_toc.json",
            "book_metadata": "11_book_metadata.json",
            "final_headings_2": "12_final_headings_2.json",
            "visual_elements": "13_visual_elements.json",
            "doubted_sections": "14_doubted_sections.json",
            "doubted_resolved": "15b_doubted_resolved.json",
            "revalidation": "15b_revalidation.json",
            "15a_heading_hierarchy": "15a_heading_hierarchy.json",
            "15c_final_book": "15c_final_book.json",
            "15d_ultimate_sections": "15d_ultimate_sections.json",
            "15e_chapter_hierarchy": "15e_chapter_hierarchy.json",
            "16_rag_snapshot": "16_rag_snapshot.json",
            "decision_trace": "decision_trace.json",
        }
        for stage_name, filename in stage_files.items():
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

"""Run stages 15a → 15d → 15e → 15f → 15c → 16 and write pipeline log artifacts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from src.shared import config
from src.modules.structure.final_structuring.book_assembler import (
    assemble_final_book,
    build_heading_hierarchy,
    build_rag_snapshot,
    build_ultimate_sections,
)
from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy
from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy
from src.modules.structure.logging.pipeline_logger import PipelineLogger
from src.shared.models import NormalizedLine


def run_final_structuring_stage(
    *,
    logger: PipelineLogger,
    lines: List[NormalizedLine],
    book_title: str,
    final_headings_2: List[Dict[str, Any]],
    fragments_log: List[Dict[str, Any]],
    metadata_line_ids: Set[int],
    toc_seed_ids: Set[int],
    first_toc_page: int,
    is_doubted: bool,
    doubted_segments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    hierarchy = build_heading_hierarchy(final_headings_2, lines=lines)
    logger.write_stage("15a_heading_hierarchy", hierarchy)

    ultimate = build_ultimate_sections(
        headings=final_headings_2,
        hierarchy=hierarchy,
        lines=lines,
        fragments=fragments_log,
        metadata_line_ids=metadata_line_ids,
        toc_seed_ids=toc_seed_ids,
    )
    logger.write_stage_payload("15d_ultimate_sections", ultimate)

    max_15e = int(getattr(config, "CHAPTER_HIERARCHY_MAX_SECTIONS", 0) or 0)
    chapter_hierarchy = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy,
        max_sections=max_15e,
    )
    logger.write_stage_payload("15e_chapter_hierarchy", chapter_hierarchy)

    chapter_hierarchy = clean_heading_hierarchy(chapter_hierarchy)
    logger.write_stage_payload("15f_heading_cleanup", chapter_hierarchy)

    final_book = assemble_final_book(
        book_title=book_title,
        first_toc_page=first_toc_page,
        is_doubted=is_doubted,
        ultimate_sections=ultimate,
        chapter_hierarchy=chapter_hierarchy,
        metadata_line_ids=metadata_line_ids,
        doubted_segments=doubted_segments,
        total_headings=len(final_headings_2),
    )
    logger.write_stage_payload("15c_final_book", final_book)

    rag = build_rag_snapshot(
        book_title=book_title,
        run_id=logger.run_id,
        ultimate_sections=ultimate,
        metadata_line_ids=metadata_line_ids,
    )
    logger.write_stage_payload("16_rag_snapshot", rag)

    return {
        "heading_hierarchy": hierarchy,
        "ultimate_sections": ultimate,
        "chapter_hierarchy": chapter_hierarchy,
        "final_book": final_book,
        "rag_snapshot": rag,
    }

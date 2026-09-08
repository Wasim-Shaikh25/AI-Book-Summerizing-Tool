"""Consolidated structure phases — four logical groups, all sub-functions preserved.

Legacy log artifacts (``s15a`` … ``s16``) are still written per sub-step so scripts,
quality audit, and older run folders keep working. See ``stage_catalog.py`` for the
human-readable name map.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from src.shared import config
from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry
from src.modules.structure.final_structuring.book_assembler import (
    assemble_final_book,
    build_heading_hierarchy,
    build_rag_snapshot,
    build_ultimate_sections,
)
from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy
# from src.modules.structure.final_structuring.chapter_placement import run_chapter_placement  # Disabled - preserve original structure
from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy
from src.modules.structure.final_structuring.hierarchy_openai_refinement import (
    run_hierarchy_openai_refinement,
)
# from src.modules.structure.final_structuring.subheading_refinement import run_heading_refinement  # Disabled - preserve original headings
from src.modules.structure.logging.pipeline_logger import PipelineLogger
from src.modules.pipeline.stage_registry import (
    STAGE_ASSEMBLE_BOOK,
    STAGE_CLEAN_TITLES,
    STAGE_CLOUD_HIERARCHY,
    STAGE_GROUP_CHAPTERS,
    STAGE_PARTITION_SECTIONS,
    STAGE_PARTITION_TREE,
    STAGE_PLACE_CHAPTERS,
    STAGE_RAG_SNAPSHOT,
    STAGE_REFINE_TITLES,
    STAGE_VALIDATE_TITLES,
)
from src.shared.models import NormalizedLine


def phase_partition(
    *,
    logger: PipelineLogger,
    lines: List[NormalizedLine],
    final_headings_2: List[Dict[str, Any]],
    fragments_log: List[Dict[str, Any]],
    metadata_line_ids: Set[int],
    toc_seed_ids: Set[int],
    document_profile: Optional[Any] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Partition: heading tree + rewrite sections."""
    hierarchy = build_heading_hierarchy(final_headings_2, lines=lines)
    logger.write_stage(STAGE_PARTITION_TREE, hierarchy)

    ultimate = build_ultimate_sections(
        headings=final_headings_2,
        hierarchy=hierarchy,
        lines=lines,
        fragments=fragments_log,
        metadata_line_ids=metadata_line_ids,
        toc_seed_ids=toc_seed_ids,
        document_profile=document_profile,
    )
    logger.write_stage_payload(STAGE_PARTITION_SECTIONS, ultimate)
    return hierarchy, ultimate


def phase_chapters(
    *,
    logger: PipelineLogger,
    hierarchy: Dict[str, Any],
    ultimate: Dict[str, Any],
    dropped_registry: Optional[DroppedHeadingRegistry],
    lines: Optional[List[NormalizedLine]] = None,
) -> Dict[str, Any]:
    """Chapters: group sections only (preserve original structure, skip placement)."""
    max_sections = int(getattr(config, "CHAPTER_HIERARCHY_MAX_SECTIONS", 0) or 0)
    chapter_hierarchy = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy,
        max_sections=max_sections,
    )
    logger.write_stage_payload(STAGE_GROUP_CHAPTERS, chapter_hierarchy)

    # Skip chapter placement (15h) - preserve original PDF structure
    # chapter_hierarchy = run_chapter_placement(chapter_hierarchy, lines=lines)
    # logger.write_stage_payload(STAGE_PLACE_CHAPTERS, chapter_hierarchy)
    return chapter_hierarchy


def phase_titles(
    *,
    logger: PipelineLogger,
    chapter_hierarchy: Dict[str, Any],
    ultimate: Dict[str, Any],
    book_title: str,
    dropped_registry: Optional[DroppedHeadingRegistry],
    lines: Optional[List[NormalizedLine]] = None,
    document_profile: Optional[Any] = None,
) -> Dict[str, Any]:
    """Titles: cleanup only (preserve original headings), optional cloud polish."""
    chapter_hierarchy = clean_heading_hierarchy(
        chapter_hierarchy,
        ultimate_sections=ultimate.get("sections") or [],
        dropped_registry=dropped_registry,
        use_llm=False,  # Disable LLM renaming, preserve original headings
    )
    logger.write_stage_payload(STAGE_CLEAN_TITLES, chapter_hierarchy)

    # Skip title refinement (15i) - preserve original headings, no renaming
    # chapter_hierarchy = run_heading_refinement(
    #     chapter_hierarchy,
    #     lines=lines,
    #     document_profile=document_profile,
    # )
    # logger.write_stage_payload(STAGE_REFINE_TITLES, chapter_hierarchy)

    if book_title:
        chapter_hierarchy["book_title"] = book_title
        meta_pre = dict(chapter_hierarchy.get("meta") or {})
        meta_pre.setdefault("book_title", book_title)
        chapter_hierarchy["meta"] = meta_pre

    chapter_hierarchy = run_hierarchy_openai_refinement(
        chapter_hierarchy,
        lines=lines,
        document_profile=document_profile,
    )
    logger.write_stage_payload(STAGE_CLOUD_HIERARCHY, chapter_hierarchy)
    return chapter_hierarchy


def phase_publish(
    *,
    logger: PipelineLogger,
    chapter_hierarchy: Dict[str, Any],
    ultimate: Dict[str, Any],
    book_title: str,
    first_toc_page: int,
    is_doubted: bool,
    metadata_line_ids: Set[int],
    doubted_segments: Optional[List[Dict[str, Any]]],
    dropped_registry: Optional[DroppedHeadingRegistry],
    final_headings_count: int,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Publish: validate titles + assemble book + RAG snapshot."""
    from src.modules.structure.final_structuring.title_validation import validate_chapter_hierarchy

    if getattr(config, "TITLE_VALIDATION_ENABLED", True):
        chapter_hierarchy = validate_chapter_hierarchy(
            chapter_hierarchy,
            ultimate_sections=ultimate.get("sections") or [],
            dropped_registry=dropped_registry,
        )
        logger.write_stage_payload(STAGE_VALIDATE_TITLES, chapter_hierarchy)

    final_book = assemble_final_book(
        book_title=book_title,
        first_toc_page=first_toc_page,
        is_doubted=is_doubted,
        ultimate_sections=ultimate,
        chapter_hierarchy=chapter_hierarchy,
        metadata_line_ids=metadata_line_ids,
        doubted_segments=doubted_segments,
        total_headings=final_headings_count,
    )
    logger.write_stage_payload(STAGE_ASSEMBLE_BOOK, final_book)

    rag = build_rag_snapshot(
        book_title=book_title,
        run_id=logger.run_id,
        ultimate_sections=ultimate,
        metadata_line_ids=metadata_line_ids,
    )
    logger.write_stage_payload(STAGE_RAG_SNAPSHOT, rag)
    return chapter_hierarchy, final_book, rag


def run_structure_phases(
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
    dropped_registry: Optional[DroppedHeadingRegistry] = None,
    document_profile: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run four consolidated structure phases; emit all legacy log artifacts."""
    hierarchy, ultimate = phase_partition(
        logger=logger,
        lines=lines,
        final_headings_2=final_headings_2,
        fragments_log=fragments_log,
        metadata_line_ids=metadata_line_ids,
        toc_seed_ids=toc_seed_ids,
        document_profile=document_profile,
    )

    chapter_hierarchy = phase_chapters(
        logger=logger,
        hierarchy=hierarchy,
        ultimate=ultimate,
        dropped_registry=dropped_registry,
        lines=lines,
    )

    chapter_hierarchy = phase_titles(
        logger=logger,
        chapter_hierarchy=chapter_hierarchy,
        ultimate=ultimate,
        book_title=book_title,
        dropped_registry=dropped_registry,
        lines=lines,
        document_profile=document_profile,
    )

    chapter_hierarchy, final_book, rag = phase_publish(
        logger=logger,
        chapter_hierarchy=chapter_hierarchy,
        ultimate=ultimate,
        book_title=book_title,
        first_toc_page=first_toc_page,
        is_doubted=is_doubted,
        metadata_line_ids=metadata_line_ids,
        doubted_segments=doubted_segments,
        dropped_registry=dropped_registry,
        final_headings_count=len(final_headings_2),
    )

    return {
        "heading_hierarchy": hierarchy,
        "ultimate_sections": ultimate,
        "chapter_hierarchy": chapter_hierarchy,
        "final_book": final_book,
        "rag_snapshot": rag,
    }

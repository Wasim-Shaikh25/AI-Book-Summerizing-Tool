"""Run stages 15a → 16 via consolidated structure_orchestrator (log keys unchanged)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry
from src.modules.structure.final_structuring.structure_orchestrator import run_structure_phases
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
    dropped_registry: Optional[DroppedHeadingRegistry] = None,
    document_profile: Optional[Any] = None,
) -> Dict[str, Any]:
    return run_structure_phases(
        logger=logger,
        lines=lines,
        book_title=book_title,
        final_headings_2=final_headings_2,
        fragments_log=fragments_log,
        metadata_line_ids=metadata_line_ids,
        toc_seed_ids=toc_seed_ids,
        first_toc_page=first_toc_page,
        is_doubted=is_doubted,
        doubted_segments=doubted_segments,
        dropped_registry=dropped_registry,
        document_profile=document_profile,
    )

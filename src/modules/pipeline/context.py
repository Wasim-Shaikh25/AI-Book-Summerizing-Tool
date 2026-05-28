"""Mutable pipeline context passed through stage plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.shared.models import FinalHeading, NormalizedLine
from src.modules.structure.logging.pipeline_logger import PipelineLogger


@dataclass
class PipelineContext:
    pdf_path: str
    enable_logs: bool = False
    persist_to_db: bool = False

    logger: PipelineLogger = field(default_factory=lambda: PipelineLogger.create(enabled=False))
    lines: List[NormalizedLine] = field(default_factory=list)
    book_title: str = ""
    visual_elements: List[Dict[str, Any]] = field(default_factory=list)
    layout_payload: List[Dict[str, Any]] = field(default_factory=list)
    layout_by_line_id: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    candidates: List[Any] = field(default_factory=list)
    headings: List[FinalHeading] = field(default_factory=list)
    fragments_result: Any = None
    fragments_log: List[Dict[str, Any]] = field(default_factory=list)
    final_headings_2_items: List[Dict[str, Any]] = field(default_factory=list)
    toc_out: List[FinalHeading] = field(default_factory=list)
    toc_seed_ids: Set[int] = field(default_factory=set)
    toc_section_line_ids: Set[int] = field(default_factory=set)
    det_toc_log_items: List[Dict[str, Any]] = field(default_factory=list)
    book_metadata_line_ids: Set[int] = field(default_factory=set)
    book_meta_log: List[Dict[str, Any]] = field(default_factory=list)
    doubted_body_ids: Set[int] = field(default_factory=set)
    doubted_toc_ids: Set[int] = field(default_factory=set)
    first_toc_page: int = 0
    stage_15b_segments: List[Dict[str, Any]] = field(default_factory=list)
    stage_15b_audits: List[Dict[str, Any]] = field(default_factory=list)
    final_headings_items: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def pdf_name(self) -> str:
        return Path(self.pdf_path).name

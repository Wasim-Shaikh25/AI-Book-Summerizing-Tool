"""Lazy RAG index build on first question (when upload skipped index)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src import config
from src.modules.generation.toc_sections import load_rewrite_sections
from src.modules.pipeline.stage_registry import STAGE_15D, STAGE_15E, STAGE_15F, resolve_existing_artifact
from src.modules.rag.service import RagService
from src.modules.storage.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


def load_book_sections(
    store: KnowledgeStore,
    *,
    book_id: str,
    pdf_path: Optional[str],
    log_dir: Optional[str],
    lines: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    ultimate_path = None
    hierarchy_path = None
    if log_dir:
        log_path = Path(log_dir)
        ultimate_path = resolve_existing_artifact(log_path, STAGE_15D)
        hierarchy_path = resolve_existing_artifact(log_path, STAGE_15F) or resolve_existing_artifact(
            log_path, STAGE_15E
        )

    return load_rewrite_sections(
        store,
        book_id=book_id,
        pdf_path=pdf_path,
        ultimate_sections_path=ultimate_path,
        chapter_hierarchy_path=hierarchy_path if hierarchy_path and hierarchy_path.exists() else None,
        lines=lines,
        prefer_15e=True,
        prefer_15d=True,
    )


def ensure_rag_index_for_book(
    store: KnowledgeStore,
    *,
    book_id: str,
    pdf_path: Optional[str] = None,
    log_dir: Optional[str] = None,
    lines: Optional[Sequence[Any]] = None,
) -> int:
    """Build FAISS index if missing. Returns chunk count (0 if skipped/disabled)."""
    if not getattr(config, "RAG_ENABLED", True):
        return 0

    rag = RagService(store)
    try:
        loaded = rag.repo.get_index_meta(book_id)
        if loaded and int(loaded.get("chunk_count") or 0) > 0:
            return int(loaded["chunk_count"])
    except Exception:
        pass

    sections = load_book_sections(
        store,
        book_id=book_id,
        pdf_path=pdf_path,
        log_dir=log_dir,
        lines=lines,
    )
    if not sections:
        logger.warning("Lazy RAG: no sections for book_id=%s", book_id)
        return 0

    try:
        idx = rag.ensure_index(book_id=book_id, sections=sections)
        return int(idx.chunk_count)
    except Exception as exc:
        logger.warning("Lazy RAG index build failed for book_id=%s: %s", book_id, exc)
        return 0

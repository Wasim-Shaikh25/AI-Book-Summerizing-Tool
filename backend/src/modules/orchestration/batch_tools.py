"""Batch tools - long-running async jobs with job_id and status polling.

These tools wrap expensive operations like full pipeline runs and corpus
index building, returning a job_id for progress tracking.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from src.modules.orchestration.models import (
    CapabilityTag,
    Tool,
    ToolInputSchema,
    ToolOutputSchema,
    ToolResult,
)
from src.modules.orchestration.tool_registry import register_tool

logger = logging.getLogger(__name__)

# Simple in-memory job store (replace with Redis/DB in production)
_job_store: dict[str, dict[str, Any]] = {}


def run_pipeline(input_data: dict[str, Any]) -> ToolResult:
    """Run the full rewrite pipeline on a document.

    This is a long-running batch operation that processes an entire document.
    Returns a job_id for status polling.

    Args:
        input_data: Should contain doc_id (book_id) and optional mode.

    Returns:
        ToolResult with job_id for tracking.
    """
    try:
        doc_id = input_data.get("doc_id")
        mode = input_data.get("mode", "study")  # "study" or "mirror"

        if not doc_id:
            return ToolResult.error_result(
                error="Missing required field: doc_id",
                tool_name="run_pipeline",
            )

        # Generate job ID
        job_id = str(uuid.uuid4())[:12]

        # Initialize job status
        _job_store[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Pipeline job queued",
            "doc_id": doc_id,
            "mode": mode,
            "created_at": time.time(),
            "result": None,
            "error": None,
        }

        # In production, this would queue the job to a worker
        # For now, we'll mark it as pending and return the job_id
        # The actual execution would happen in a background process

        output = {
            "job_id": job_id,
            "status": "pending",
            "message": "Pipeline job started. Poll /api/jobs/{job_id} for progress.",
            "estimated_time_minutes": 15,
        }

        logger.info("Pipeline job queued: %s for doc %s (mode: %s)", job_id, doc_id, mode)

        return ToolResult.success_result(
            output=output, job_id=job_id, tool_name="run_pipeline"
        )

    except Exception as exc:
        logger.exception("run_pipeline failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="run_pipeline")


def build_corpus_index(input_data: dict[str, Any]) -> ToolResult:
    """Build a corpus-level FAISS index across multiple books.

    This enables cross-book search. Returns a job_id for tracking.

    Args:
        input_data: Should contain book_ids (list) and user_id.

    Returns:
        ToolResult with job_id for tracking.
    """
    try:
        from src.modules.rag.corpus_builder import build_corpus_index as _build_corpus
        from src.modules.rag.service import RagService

        book_ids = input_data.get("book_ids", [])
        user_id = input_data.get("user_id")

        if not book_ids:
            return ToolResult.error_result(
                error="Missing required field: book_ids",
                tool_name="build_corpus_index",
            )

        if not user_id:
            return ToolResult.error_result(
                error="Missing required field: user_id",
                tool_name="build_corpus_index",
            )

        # Generate job ID
        job_id = str(uuid.uuid4())[:12]

        # Initialize job status
        _job_store[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Corpus index build queued",
            "book_ids": book_ids,
            "user_id": user_id,
            "created_at": time.time(),
            "result": None,
            "error": None,
        }

        # In production, this would queue to a worker
        # For synchronous execution (for now):
        try:
            rag = RagService()

            class _RepoAdapter:
                """Adapts RagRepository.list_chunks to the get_chunks interface expected by corpus_builder."""

                def __init__(self, repo):
                    self._repo = repo

                def get_chunks(self, book_id):
                    return self._repo.list_chunks(book_id)

            # Build the corpus index
            _build_corpus(
                book_ids,
                user_id,
                data_dir=rag.index_dir,
                rag_repo=_RepoAdapter(rag.repo),
                embedding_model="all-MiniLM-L6-v2",
            )

            _job_store[job_id]["status"] = "done"
            _job_store[job_id]["progress"] = 100
            _job_store[job_id]["message"] = "Corpus index built successfully"
            _job_store[job_id]["result"] = {"book_count": len(book_ids)}

            logger.info("Corpus index built: %s for %s", job_id, book_ids)

        except Exception as exc:
            _job_store[job_id]["status"] = "error"
            _job_store[job_id]["error"] = str(exc)
            _job_store[job_id]["message"] = "Corpus index build failed"
            logger.exception("Corpus index build failed: %s", exc)

        output = {
            "job_id": job_id,
            "status": _job_store[job_id]["status"],
            "message": _job_store[job_id]["message"],
            "book_count": len(book_ids),
        }

        return ToolResult.success_result(
            output=output, job_id=job_id, tool_name="build_corpus_index"
        )

    except Exception as exc:
        logger.exception("build_corpus_index failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="build_corpus_index")


def get_job_status(job_id: str) -> dict[str, Any]:
    """Get the status of a batch job.

    Args:
        job_id: Job identifier.

    Returns:
        Job status dict.
    """
    job = _job_store.get(job_id)
    if not job:
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Job not found",
        }
    return job


def register_batch_tools() -> None:
    """Register all batch tools in the global registry."""

    # run_pipeline
    register_tool(
        Tool(
            name="run_pipeline",
            description="Run the full rewrite pipeline on a document. Long-running batch operation returning a job_id.",
            input_schema=ToolInputSchema(
                properties={
                    "doc_id": {"type": "string", "description": "Document/book identifier"},
                    "mode": {"type": "string", "description": "Pipeline mode: 'study' or 'mirror'"},
                },
                required=["doc_id"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "job_id": {"type": "string"},
                    "status": {"type": "string"},
                    "message": {"type": "string"},
                    "estimated_time_minutes": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.BATCH, CapabilityTag.WRITE},
            estimated_cost_seconds=900.0,  # 15 minutes
            is_write=True,
            is_batch=True,
            executor=run_pipeline,
        )
    )

    # build_corpus_index
    register_tool(
        Tool(
            name="build_corpus_index",
            description="Build a corpus-level FAISS index across multiple books for cross-book search. Returns job_id.",
            input_schema=ToolInputSchema(
                properties={
                    "book_ids": {"type": "array", "description": "List of book IDs to include"},
                    "user_id": {"type": "string", "description": "Owner user ID"},
                },
                required=["book_ids", "user_id"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "job_id": {"type": "string"},
                    "status": {"type": "string"},
                    "message": {"type": "string"},
                    "book_count": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.BATCH, CapabilityTag.WRITE},
            estimated_cost_seconds=60.0,  # 1 minute
            is_write=True,
            is_batch=True,
            executor=build_corpus_index,
        )
    )


# Auto-register on import
register_batch_tools()

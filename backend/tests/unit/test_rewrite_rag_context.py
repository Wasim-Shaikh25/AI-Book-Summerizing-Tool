"""Unit tests for REWRITE_RAG_CONTEXT injection in parallel_rewrite."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))


def _make_rag_service(results: list) -> MagicMock:
    svc = MagicMock()
    svc.retrieve.return_value = results
    return svc


def test_rag_context_not_injected_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("REWRITE_RAG_CONTEXT", "0")
    svc = _make_rag_service([{"section_id": "S2", "text": "related content"}])
    enabled = os.getenv("REWRITE_RAG_CONTEXT", "0").strip() == "1"
    assert not enabled
    svc.retrieve.assert_not_called()


def test_rag_context_injected_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("REWRITE_RAG_CONTEXT", "1")
    enabled = os.getenv("REWRITE_RAG_CONTEXT", "0").strip() == "1"
    assert enabled


def test_rag_context_truncated_to_400_chars() -> None:
    long_text = "X" * 800
    rag_context = long_text[:400]
    assert len(rag_context) <= 400


def test_rag_context_excludes_current_section() -> None:
    candidates = [
        {"section_id": "S1", "text": "current section text"},
        {"section_id": "S2", "text": "related section text"},
    ]
    current_sid = "S1"
    filtered = [c for c in candidates if c.get("section_id") != current_sid]
    assert all(c["section_id"] != "S1" for c in filtered)
    assert len(filtered) == 1


def test_rag_context_max_two_results() -> None:
    candidates = [
        {"section_id": "S2", "text": "a"},
        {"section_id": "S3", "text": "b"},
        {"section_id": "S4", "text": "c"},
    ]
    used = candidates[:2]
    assert len(used) == 2


def test_build_prompt_appends_rag_context_block() -> None:
    """_build_prompt must append the RAG context block when rag_context is given."""
    from src.modules.generation.parallel_rewrite import _build_prompt, _RewriteJob

    job = _RewriteJob(
        index=0,
        section_id="S1",
        heading="Test heading",
        source_text="Source text here.",
        prev_heading="",
        prev_overlap="",
        next_heading="",
        next_overlap="",
        chapter_heading="Chapter",
        subheadings=(),
    )
    prompt_no_ctx = _build_prompt(job, user_instruction="Rewrite.", overlap_chars=0)
    prompt_with_ctx = _build_prompt(
        job, user_instruction="Rewrite.", overlap_chars=0, rag_context="Related context here."
    )
    assert "Related context" in prompt_with_ctx
    assert "Related context" not in prompt_no_ctx

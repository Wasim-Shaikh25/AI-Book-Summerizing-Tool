"""Tests for ingestion profile overrides."""

from __future__ import annotations

import os

from src.modules.ingestion.profile import ingestion_profile_context, profile_overrides, upload_skip_rag_default


def test_fast_local_profile_overrides() -> None:
    overrides = profile_overrides("fast_local")
    assert overrides["DOUBTED_RESOLVER_LLM"] == "off"
    assert overrides["DOUBTED_RESOLVER_MODE"] == "fast"
    assert overrides["CHAPTER_HIERARCHY_USE_LLM"] == "false"
    assert overrides["HEADING_CLEANUP_BACKEND"] == "rules_only"
    assert overrides["UPLOAD_SKIP_RAG"] == "true"
    assert overrides["OCR_ZOOM"] == "1.5"


def test_ingestion_profile_context_applies_and_restores() -> None:
    prev_zoom = os.environ.get("OCR_ZOOM")
    with ingestion_profile_context("fast_local"):
        assert os.environ.get("OCR_ZOOM") == "1.5"
        assert os.environ.get("HEADING_CLEANUP_BACKEND") == "rules_only"
    assert os.environ.get("OCR_ZOOM") == prev_zoom


def test_upload_skip_rag_default_fast_local() -> None:
    with ingestion_profile_context("fast_local"):
        assert upload_skip_rag_default() is True

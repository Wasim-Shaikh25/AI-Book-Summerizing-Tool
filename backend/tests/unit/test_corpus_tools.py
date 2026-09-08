"""Tests for corpus research tools."""

from __future__ import annotations

import pytest

from src.modules.orchestration.corpus_tools import (
    analyze_corpus_trends,
    compare_documents,
    map_outline_to_corpus,
)


def test_map_outline_to_corpus_missing_outline():
    """Test map_outline_to_corpus with missing outline."""
    result = map_outline_to_corpus({})
    assert not result.success
    assert "Missing required field: outline" in result.error


def test_analyze_corpus_trends_missing_items():
    """Test analyze_corpus_trends with missing items."""
    result = analyze_corpus_trends({})
    assert not result.success
    assert "Missing required field: extracted_items" in result.error


def test_compare_documents_missing_documents():
    """Test compare_documents with missing documents."""
    result = compare_documents({})
    assert not result.success
    assert "Missing required field: doc_ids" in result.error

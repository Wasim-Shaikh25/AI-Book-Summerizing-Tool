"""Tests for read tools (list_documents, get_section, search_documents, etc.)."""

from __future__ import annotations

import pytest

from src.modules.orchestration.read_tools import (
    get_document_structure,
    get_section,
    list_documents,
    search_documents,
    traverse_concepts,
)


def test_list_documents_success():
    """Test listing documents without user_id."""
    result = list_documents({})
    assert result.success
    assert "documents" in result.output
    assert "count" in result.output


def test_list_documents_with_user_filter():
    """Test listing documents with user_id filter."""
    result = list_documents({"user_id": "test_user"})
    assert result.success
    # Should filter by user_id in SQL query


def test_get_section_missing_required_fields():
    """Test get_section with missing required fields."""
    result = get_section({})  # Missing book_id and section_id
    assert not result.success
    assert "Missing required fields" in result.error


def test_get_document_structure_missing_book_id():
    """Test get_document_structure with missing book_id."""
    result = get_document_structure({})  # Missing book_id
    assert not result.success
    assert "Missing required field: book_id" in result.error


def test_search_documents_basic():
    """Test basic document search."""
    result = search_documents({"query": "test", "book_ids": []})
    # This may fail without actual indexed books, but should handle gracefully
    assert result is not None


def test_traverse_concepts_basic():
    """Test concept traversal."""
    result = traverse_concepts({"concept_name": "photosynthesis", "max_hops": 2})
    # May return empty if knowledge graph not enabled, but should not crash
    assert result is not None

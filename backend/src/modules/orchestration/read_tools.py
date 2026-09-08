"""Read tools - thin wrappers around existing retrieval functionality.

These tools expose existing RAG, document store, and knowledge graph capabilities
as typed parametric tools for the agent to use.
"""

from __future__ import annotations

import logging
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


def list_documents(input_data: dict[str, Any]) -> ToolResult:
    """List all documents (books) available to the user.

    Args:
        input_data: Should contain optional user_id for scoping.

    Returns:
        ToolResult with list of documents (book_id, title, total_pages, etc.).
    """
    try:
        from src.modules.storage.knowledge_store import KnowledgeStore

        user_id = input_data.get("user_id")
        store = KnowledgeStore()
        conn = store.get_connection()
        try:
            cur = conn.cursor()
            if user_id:
                cur.execute(
                    "SELECT b.book_id, b.title FROM books b "
                    "JOIN user_books ub ON ub.book_id = b.book_id WHERE ub.user_id = ?",
                    (user_id,),
                )
            else:
                cur.execute("SELECT book_id, title FROM books")
            rows = cur.fetchall()
        finally:
            conn.close()

        output = {
            "documents": [
                {"book_id": row[0], "title": row[1]}
                for row in rows
            ],
            "count": len(rows),
        }

        return ToolResult.success_result(output=output, tool_name="list_documents")

    except Exception as exc:
        logger.exception("list_documents failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="list_documents")


def get_section(input_data: dict[str, Any]) -> ToolResult:
    """Get a specific section from a document.

    Args:
        input_data: Should contain book_id and section_id.

    Returns:
        ToolResult with section content (heading, body, page numbers, etc.).
    """
    try:
        from services.rag_index_helper import load_book_sections
        from src.modules.storage.knowledge_store import KnowledgeStore

        book_id = input_data.get("book_id")
        section_id = input_data.get("section_id")

        if not book_id or not section_id:
            return ToolResult.error_result(
                error="Missing required fields: book_id, section_id",
                tool_name="get_section",
            )

        sections = load_book_sections(
            KnowledgeStore(), book_id=book_id, pdf_path=None, log_dir=None
        )

        # Find the specific section
        section = None
        for s in sections:
            if s.get("section_id") == section_id:
                section = s
                break

        if not section:
            return ToolResult.error_result(
                error=f"Section {section_id} not found in book {book_id}",
                tool_name="get_section",
            )

        output = {
            "section_id": section.get("section_id"),
            "heading": section.get("heading"),
            "body": section.get("text", "")[:10000],  # Limit size
            "page_start": section.get("page_start"),
            "page_end": section.get("page_end"),
            "chapter": section.get("chapter"),
        }

        citations = [
            {
                "section_id": section.get("section_id"),
                "heading": section.get("heading"),
                "page": section.get("page_start"),
            }
        ]

        return ToolResult.success_result(
            output=output, citations=citations, tool_name="get_section"
        )

    except Exception as exc:
        logger.exception("get_section failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="get_section")


def get_document_structure(input_data: dict[str, Any]) -> ToolResult:
    """Get the hierarchical structure (TOC) of a document.

    Args:
        input_data: Should contain book_id.

    Returns:
        ToolResult with document structure (chapters, sections, hierarchy).
    """
    try:
        from services.rag_index_helper import load_book_sections
        from src.modules.storage.knowledge_store import KnowledgeStore

        book_id = input_data.get("book_id")

        if not book_id:
            return ToolResult.error_result(
                error="Missing required field: book_id",
                tool_name="get_document_structure",
            )

        sections = load_book_sections(
            KnowledgeStore(), book_id=book_id, pdf_path=None, log_dir=None
        )

        # Build hierarchical structure
        structure = []
        current_chapter = None

        for s in sections:
            chapter = s.get("chapter")
            if chapter and chapter != current_chapter:
                current_chapter = chapter
                structure.append(
                    {
                        "type": "chapter",
                        "title": chapter,
                        "sections": [],
                    }
                )

            if structure:
                structure[-1]["sections"].append(
                    {
                        "section_id": s.get("section_id"),
                        "heading": s.get("heading"),
                        "page_start": s.get("page_start"),
                    }
                )

        output = {
            "book_id": book_id,
            "structure": structure,
            "total_sections": len(sections),
        }

        return ToolResult.success_result(output=output, tool_name="get_document_structure")

    except Exception as exc:
        logger.exception("get_document_structure failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="get_document_structure")


def search_documents(input_data: dict[str, Any]) -> ToolResult:
    """Search across documents using RAG retrieval.

    Args:
        input_data: Should contain query, optional book_id, optional user_id,
                   optional cross_book flag.

    Returns:
        ToolResult with relevant chunks and citations.
    """
    try:
        from src.modules.rag.service import RagService

        query = input_data.get("query")
        book_id = input_data.get("book_id")
        user_id = input_data.get("user_id")
        cross_book = input_data.get("cross_book", False)
        top_k = input_data.get("top_k", 6)

        if not query:
            return ToolResult.error_result(
                error="Missing required field: query",
                tool_name="search_documents",
            )

        rag = RagService()

        if cross_book and user_id:
            # Cross-book corpus search
            results = rag.retrieve_cross_book(query, user_id, book_ids=None, top_k=top_k)
        elif book_id:
            # Single-book search
            results = rag.retrieve(query, book_id=book_id, sections=[], top_k=top_k)
        else:
            return ToolResult.error_result(
                error="Either book_id or user_id (for cross_book) is required",
                tool_name="search_documents",
            )

        # Format output with citations
        chunks = []
        citations = []

        for r in results:
            chunk = {
                "section_id": r.get("section_id") or r.get("chunk_id"),
                "heading": r.get("heading"),
                "excerpt": r.get("text", "")[:500],  # Truncate for preview
                "score": r.get("score", 0),
                "book_id": r.get("book_id"),
            }
            chunks.append(chunk)

            citations.append(
                {
                    "section_id": chunk["section_id"],
                    "heading": chunk["heading"],
                    "page": r.get("page_start"),
                    "book_id": chunk["book_id"],
                }
            )

        output = {
            "query": query,
            "chunks": chunks,
            "count": len(chunks),
            "cross_book": cross_book,
        }

        return ToolResult.success_result(
            output=output, citations=citations, tool_name="search_documents"
        )

    except Exception as exc:
        logger.exception("search_documents failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="search_documents")


def traverse_concepts(input_data: dict[str, Any]) -> ToolResult:
    """Traverse the knowledge graph to find related concepts and sections.

    Args:
        input_data: Should contain concept_name or query, optional max_hops.

    Returns:
        ToolResult with related concepts and evidence sections.
    """
    try:
        from src.modules.knowledge.concept_graph import get_concept_by_name, get_related_concepts
        from src.modules.knowledge.graph_retriever import retrieve_with_graph
        from pathlib import Path

        from src import config as cfg

        concept_name = input_data.get("concept_name")
        query = input_data.get("query")
        max_hops = input_data.get("max_hops", 2)

        if not concept_name and not query:
            return ToolResult.error_result(
                error="Either concept_name or query is required",
                tool_name="traverse_concepts",
            )

        db_path = Path(getattr(cfg, "KNOWLEDGE_DB_PATH", "output/knowledge_base.db"))

        # If query provided, use graph retrieval
        if query:
            from src.modules.rag.service import RagService

            book_id = input_data.get("book_id")
            rag = RagService()

            chunks = retrieve_with_graph(
                query,
                rag,
                db_path=db_path,
                book_id=book_id,
                max_hops=max_hops,
                top_k_chunks=8,
            )

            citations = [
                {
                    "section_id": c.get("section_id") or c.get("chunk_id"),
                    "heading": c.get("heading"),
                    "page": c.get("page_start"),
                }
                for c in chunks
            ]

            output = {
                "query": query,
                "chunks": chunks,
                "count": len(chunks),
            }

            return ToolResult.success_result(
                output=output, citations=citations, tool_name="traverse_concepts"
            )

        # If concept_name provided, traverse graph directly
        concept = get_concept_by_name(concept_name, db_path=db_path)
        if not concept:
            return ToolResult.error_result(
                error=f"Concept '{concept_name}' not found",
                tool_name="traverse_concepts",
            )

        related = get_related_concepts(concept["concept_id"], db_path=db_path, max_hops=max_hops)

        output = {
            "concept": {
                "canonical_name": concept["canonical_name"],
                "concept_id": concept["concept_id"],
            },
            "related_concepts": related,
            "count": len(related),
        }

        return ToolResult.success_result(output=output, tool_name="traverse_concepts")

    except Exception as exc:
        logger.exception("traverse_concepts failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="traverse_concepts")


def register_read_tools() -> None:
    """Register all read tools in the global registry."""

    # list_documents
    register_tool(
        Tool(
            name="list_documents",
            description="List all documents (books) available to the user, including titles and metadata.",
            input_schema=ToolInputSchema(
                properties={
                    "user_id": {"type": "string", "description": "Optional user ID for scoping"},
                }
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "documents": {"type": "array", "description": "List of documents"},
                    "count": {"type": "integer", "description": "Total count"},
                }
            ),
            capability_tags={CapabilityTag.READ},
            estimated_cost_seconds=0.5,
            executor=list_documents,
        )
    )

    # get_section
    register_tool(
        Tool(
            name="get_section",
            description="Get a specific section from a document by section_id.",
            input_schema=ToolInputSchema(
                properties={
                    "book_id": {"type": "string", "description": "Book identifier"},
                    "section_id": {"type": "string", "description": "Section identifier"},
                },
                required=["book_id", "section_id"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "section_id": {"type": "string"},
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                    "page_start": {"type": "integer"},
                    "page_end": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.READ},
            estimated_cost_seconds=0.3,
            executor=get_section,
        )
    )

    # get_document_structure
    register_tool(
        Tool(
            name="get_document_structure",
            description="Get the hierarchical table of contents structure of a document.",
            input_schema=ToolInputSchema(
                properties={
                    "book_id": {"type": "string", "description": "Book identifier"},
                },
                required=["book_id"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "book_id": {"type": "string"},
                    "structure": {"type": "array", "description": "Hierarchical structure"},
                    "total_sections": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.READ},
            estimated_cost_seconds=0.5,
            executor=get_document_structure,
        )
    )

    # search_documents
    register_tool(
        Tool(
            name="search_documents",
            description="Search across documents using semantic retrieval. Supports single-book or cross-book search.",
            input_schema=ToolInputSchema(
                properties={
                    "query": {"type": "string", "description": "Search query"},
                    "book_id": {"type": "string", "description": "Optional book ID for single-book search"},
                    "user_id": {"type": "string", "description": "Optional user ID for cross-book search"},
                    "cross_book": {"type": "boolean", "description": "Enable cross-book corpus search"},
                    "top_k": {"type": "integer", "description": "Number of results to return"},
                },
                required=["query"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "query": {"type": "string"},
                    "chunks": {"type": "array", "description": "Retrieved chunks"},
                    "count": {"type": "integer"},
                    "cross_book": {"type": "boolean"},
                }
            ),
            capability_tags={CapabilityTag.READ, CapabilityTag.SEARCH, CapabilityTag.RETRIEVAL},
            estimated_cost_seconds=1.0,
            executor=search_documents,
        )
    )

    # traverse_concepts
    register_tool(
        Tool(
            name="traverse_concepts",
            description="Traverse the knowledge graph to find related concepts and evidence sections.",
            input_schema=ToolInputSchema(
                properties={
                    "concept_name": {"type": "string", "description": "Concept name to look up"},
                    "query": {"type": "string", "description": "Query for graph-augmented retrieval"},
                    "book_id": {"type": "string", "description": "Optional book ID for scoping"},
                    "max_hops": {"type": "integer", "description": "Maximum graph hops"},
                },
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "concept": {"type": "object"},
                    "related_concepts": {"type": "array"},
                    "count": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.READ, CapabilityTag.RETRIEVAL, CapabilityTag.ANALYSIS},
            estimated_cost_seconds=1.5,
            executor=traverse_concepts,
        )
    )


# Auto-register on import
register_read_tools()

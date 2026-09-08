"""Extraction tools - generic structured extraction with user-defined schemas.

The extract_items tool is a domain-agnostic replacement for hardcoded parsers.
It can extract questions, dates, definitions, formulas, clauses, etc. based on
a user-provided schema.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.modules.orchestration.models import (
    CapabilityTag,
    Tool,
    ToolInputSchema,
    ToolOutputSchema,
    ToolResult,
)
from src.modules.orchestration.tool_registry import register_tool

logger = logging.getLogger(__name__)


def extract_items(input_data: dict[str, Any]) -> ToolResult:
    """Extract structured items from a document based on a user-defined schema.

    This is a domain-agnostic extraction tool. Examples:
    - Extract questions from an assessment document
    - Extract definitions from a medical textbook
    - Extract clauses from a legal contract
    - Extract formulas from an engineering manual
    - Extract dates from a historical document

    Args:
        input_data: Should contain doc_id, item_schema (JSON schema describing
                   what to extract), and instruction (natural language description).

    Returns:
        ToolResult with extracted items and citations.
    """
    try:
        from services.rag_index_helper import load_book_sections
        from src.modules.generation.model_router import RewriteModelRouter
        from src.modules.storage.knowledge_store import KnowledgeStore

        doc_id = input_data.get("doc_id")
        item_schema = input_data.get("item_schema", {})
        instruction = input_data.get("instruction")

        if not doc_id:
            return ToolResult.error_result(
                error="Missing required field: doc_id",
                tool_name="extract_items",
            )

        if not instruction:
            return ToolResult.error_result(
                error="Missing required field: instruction",
                tool_name="extract_items",
            )

        # Get document content
        sections = load_book_sections(
            KnowledgeStore(), book_id=doc_id, pdf_path=None, log_dir=None
        )

        if not sections:
            return ToolResult.error_result(
                error=f"No sections found for document {doc_id}",
                tool_name="extract_items",
            )

        # Build context from sections (limit to first 20 sections for performance)
        context_parts = []
        for i, s in enumerate(sections[:20]):
            heading = s.get("heading", "")
            text = s.get("text", "")[:2000]  # Truncate
            context_parts.append(f"[{i+1}] {heading}\n{text}")

        context = "\n\n".join(context_parts)

        # Build extraction prompt
        schema_description = json.dumps(item_schema, indent=2) if item_schema else "Use a JSON array of objects"

        system_prompt = (
            "You are a structured data extractor. Extract items from the provided document "
            "according to the user's instruction.\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            f"{schema_description}\n\n"
            "Rules:\n"
            "- Extract ALL matching items found in the text\n"
            "- Include section_id or page references for each item if possible\n"
            "- Return empty array [] if no items are found\n"
            "- Do not include explanations outside the JSON"
        )

        user_prompt = (
            f"Instruction: {instruction}\n\n"
            f"Document content:\n{context}\n\n"
            f"Extract items according to the instruction. Return JSON only."
        )

        # Generate extraction
        router = RewriteModelRouter()
        result = router.generate(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=4000)

        raw_output = result.get("text", "").strip()

        # Parse JSON output
        try:
            # Try to extract JSON from the response (in case of extra text)
            if "```json" in raw_output:
                json_start = raw_output.find("```json") + 7
                json_end = raw_output.find("```", json_start)
                json_str = raw_output[json_start:json_end].strip()
            elif "```" in raw_output:
                json_start = raw_output.find("```") + 3
                json_end = raw_output.find("```", json_start)
                json_str = raw_output[json_start:json_end].strip()
            else:
                json_str = raw_output

            extracted = json.loads(json_str)

            if not isinstance(extracted, list):
                extracted = [extracted]

        except json.JSONDecodeError:
            # Fallback: return raw text as single item
            extracted = [{"raw_extraction": raw_output}]

        # Build citations
        citations = [
            {
                "section_id": s.get("section_id"),
                "heading": s.get("heading"),
                "page": s.get("page_start"),
            }
            for s in sections[:20]
        ]

        output = {
            "doc_id": doc_id,
            "instruction": instruction,
            "extracted_items": extracted,
            "item_count": len(extracted),
            "sections_processed": min(20, len(sections)),
        }

        return ToolResult.success_result(
            output=output, citations=citations, tool_name="extract_items"
        )

    except Exception as exc:
        logger.exception("extract_items failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="extract_items")


def register_extraction_tools() -> None:
    """Register extraction tools in the global registry."""

    # extract_items
    register_tool(
        Tool(
            name="extract_items",
            description="Extract structured items from a document based on a user-defined schema. Can extract questions, definitions, dates, clauses, formulas, etc. Domain-agnostic.",
            input_schema=ToolInputSchema(
                properties={
                    "doc_id": {"type": "string", "description": "Document/book identifier"},
                    "item_schema": {"type": "object", "description": "JSON schema describing item structure"},
                    "instruction": {"type": "string", "description": "Natural language instruction for what to extract"},
                },
                required=["doc_id", "instruction"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "doc_id": {"type": "string"},
                    "instruction": {"type": "string"},
                    "extracted_items": {"type": "array"},
                    "item_count": {"type": "integer"},
                    "sections_processed": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.READ, CapabilityTag.ANALYSIS},
            estimated_cost_seconds=5.0,
            executor=extract_items,
        )
    )


# Auto-register on import
register_extraction_tools()

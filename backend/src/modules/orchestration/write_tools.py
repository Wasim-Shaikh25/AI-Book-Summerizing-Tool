"""Write tools - parametric tools for content generation and export.

These tools allow the agent to:
- Rewrite sections with custom instructions (diagram-friendly, story-style, etc.)
- Generate content from context chunks
- Export to DOCX and Markdown formats
"""

from __future__ import annotations

import logging
import time
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


def rewrite_section(input_data: dict[str, Any]) -> ToolResult:
    """Rewrite a section with a custom instruction.

    The instruction is a free-form string that passes through to the rewrite
    prompts' guardrails. Examples: "use diagrams", "story-style narrative",
    "table-only format", "compare with X".

    Args:
        input_data: Should contain book_id, section_id, and instruction.

    Returns:
        ToolResult with rewritten content and citations.
    """
    try:
        from services.rag_index_helper import load_book_sections
        from src.modules.generation.model_router import RewriteModelRouter
        from src.modules.generation.rewrite_prompts import (
            build_dynamic_rewrite_system_prompt,
            build_section_user_prompt,
        )
        from src.modules.storage.knowledge_store import KnowledgeStore

        book_id = input_data.get("book_id")
        section_id = input_data.get("section_id")
        instruction = input_data.get("instruction")

        if not book_id or not section_id or not instruction:
            return ToolResult.error_result(
                error="Missing required fields: book_id, section_id, instruction",
                tool_name="rewrite_section",
            )

        # Get section content
        sections = load_book_sections(
            KnowledgeStore(), book_id=book_id, pdf_path=None, log_dir=None
        )
        section = None
        for s in sections:
            if s.get("section_id") == section_id:
                section = s
                break

        if not section:
            return ToolResult.error_result(
                error=f"Section {section_id} not found",
                tool_name="rewrite_section",
            )

        # Build prompt with custom instruction
        heading = section.get("heading", "")
        text = section.get("text", "")

        system_prompt = build_dynamic_rewrite_system_prompt(user_instruction=instruction)
        user_prompt = build_section_user_prompt(
            user_instruction=instruction,
            heading=heading,
            source_text=text,
        )

        # Generate rewrite
        router = RewriteModelRouter()
        result = router.generate(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=2000)

        rewritten = result.get("text", "").strip()

        citations = [
            {
                "section_id": section_id,
                "heading": heading,
                "page": section.get("page_start"),
            }
        ]

        output = {
            "section_id": section_id,
            "heading": heading,
            "rewritten_content": rewritten,
            "instruction": instruction,
        }

        return ToolResult.success_result(
            output=output, citations=citations, tool_name="rewrite_section"
        )

    except Exception as exc:
        logger.exception("rewrite_section failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="rewrite_section")


def generate_content(input_data: dict[str, Any]) -> ToolResult:
    """Generate content from context chunks with a custom instruction.

    This is a free-form generation tool that can create summaries, explanations,
    comparisons, tables, or any structured content based on provided context.

    Args:
        input_data: Should contain instruction and context_chunks (array of text).

    Returns:
        ToolResult with generated content and citations.
    """
    try:
        from src.modules.generation.model_router import RewriteModelRouter

        instruction = input_data.get("instruction")
        context_chunks = input_data.get("context_chunks", [])

        if not instruction:
            return ToolResult.error_result(
                error="Missing required field: instruction",
                tool_name="generate_content",
            )

        if not context_chunks:
            return ToolResult.error_result(
                error="Missing required field: context_chunks",
                tool_name="generate_content",
            )

        # Build context block
        context_block = "\n\n---\n\n".join(context_chunks)

        system_prompt = (
            f"You are a content generator. Follow the user's instruction exactly.\n"
            f"Instruction: {instruction}\n\n"
            f"Use the provided context as source material. "
            f"Do not invent facts. Cite sources when applicable."
        )

        user_prompt = f"Context:\n{context_block}\n\nGenerate content according to the instruction."

        router = RewriteModelRouter()
        result = router.generate(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=3000)

        generated = result.get("text", "").strip()

        output = {
            "instruction": instruction,
            "generated_content": generated,
            "context_count": len(context_chunks),
        }

        return ToolResult.success_result(output=output, tool_name="generate_content")

    except Exception as exc:
        logger.exception("generate_content failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="generate_content")


def export_docx(input_data: dict[str, Any]) -> ToolResult:
    """Export content to DOCX format.

    Args:
        input_data: Should contain content (markdown or text) and optional filename.

    Returns:
        ToolResult with artifact path to the DOCX file.
    """
    try:
        from src.modules.export.markdown_docx_renderer import export_markdown_file_to_docx

        content = input_data.get("content")
        filename = input_data.get("filename", "export.docx")

        if not content:
            return ToolResult.error_result(
                error="Missing required field: content",
                tool_name="export_docx",
            )

        # Create artifact directory
        artifact_dir = Path("output/tool_artifacts")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = int(time.time())
        safe_filename = f"{timestamp}_{filename}"
        output_path = artifact_dir / safe_filename

        # Export markdown content to DOCX using existing renderer
        export_markdown_file_to_docx(content, output_path)

        output = {
            "filename": safe_filename,
            "format": "docx",
            "char_count": len(content),
        }

        return ToolResult.success_result(
            output=output, artifact_path=str(output_path), tool_name="export_docx"
        )

    except Exception as exc:
        logger.exception("export_docx failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="export_docx")


def export_markdown(input_data: dict[str, Any]) -> ToolResult:
    """Export content to Markdown format.

    Args:
        input_data: Should contain content (markdown or text) and optional filename.

    Returns:
        ToolResult with artifact path to the Markdown file.
    """
    try:
        content = input_data.get("content")
        filename = input_data.get("filename", "export.md")

        if not content:
            return ToolResult.error_result(
                error="Missing required field: content",
                tool_name="export_markdown",
            )

        # Create artifact directory
        artifact_dir = Path("output/tool_artifacts")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = int(time.time())
        safe_filename = f"{timestamp}_{filename}"
        output_path = artifact_dir / safe_filename

        # Write markdown file
        output_path.write_text(content, encoding="utf-8")

        output = {
            "filename": safe_filename,
            "format": "markdown",
            "char_count": len(content),
        }

        return ToolResult.success_result(
            output=output, artifact_path=str(output_path), tool_name="export_markdown"
        )

    except Exception as exc:
        logger.exception("export_markdown failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="export_markdown")


def register_write_tools() -> None:
    """Register all write tools in the global registry."""

    # rewrite_section
    register_tool(
        Tool(
            name="rewrite_section",
            description="Rewrite a section with a custom instruction. Supports diagram-friendly, story-style, table-only, or any custom format.",
            input_schema=ToolInputSchema(
                properties={
                    "book_id": {"type": "string", "description": "Book identifier"},
                    "section_id": {"type": "string", "description": "Section identifier"},
                    "instruction": {"type": "string", "description": "Custom instruction for rewrite (e.g., 'use diagrams', 'story-style')"},
                },
                required=["book_id", "section_id", "instruction"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "section_id": {"type": "string"},
                    "heading": {"type": "string"},
                    "rewritten_content": {"type": "string"},
                    "instruction": {"type": "string"},
                }
            ),
            capability_tags={CapabilityTag.WRITE, CapabilityTag.GENERATION},
            estimated_cost_seconds=3.0,
            is_write=True,
            executor=rewrite_section,
        )
    )

    # generate_content
    register_tool(
        Tool(
            name="generate_content",
            description="Generate content from context chunks with a custom instruction. Can create summaries, explanations, comparisons, tables, etc.",
            input_schema=ToolInputSchema(
                properties={
                    "instruction": {"type": "string", "description": "Instruction for content generation"},
                    "context_chunks": {"type": "array", "description": "Array of context text chunks"},
                },
                required=["instruction", "context_chunks"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "instruction": {"type": "string"},
                    "generated_content": {"type": "string"},
                    "context_count": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.WRITE, CapabilityTag.GENERATION},
            estimated_cost_seconds=4.0,
            is_write=True,
            executor=generate_content,
        )
    )

    # export_docx
    register_tool(
        Tool(
            name="export_docx",
            description="Export content to DOCX format.",
            input_schema=ToolInputSchema(
                properties={
                    "content": {"type": "string", "description": "Content to export (markdown or text)"},
                    "filename": {"type": "string", "description": "Optional filename (default: export.docx)"},
                    "title": {"type": "string", "description": "Optional document title"},
                },
                required=["content"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "filename": {"type": "string"},
                    "format": {"type": "string"},
                    "section_count": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.WRITE, CapabilityTag.EXPORT},
            estimated_cost_seconds=1.0,
            is_write=True,
            executor=export_docx,
        )
    )

    # export_markdown
    register_tool(
        Tool(
            name="export_markdown",
            description="Export content to Markdown format.",
            input_schema=ToolInputSchema(
                properties={
                    "content": {"type": "string", "description": "Content to export (markdown or text)"},
                    "filename": {"type": "string", "description": "Optional filename (default: export.md)"},
                },
                required=["content"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "filename": {"type": "string"},
                    "format": {"type": "string"},
                    "char_count": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.WRITE, CapabilityTag.EXPORT},
            estimated_cost_seconds=0.5,
            is_write=True,
            executor=export_markdown,
        )
    )


# Auto-register on import
register_write_tools()

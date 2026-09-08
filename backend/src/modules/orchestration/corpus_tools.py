"""Corpus research tools - multi-document, outline-driven research capabilities.

These tools enable:
- Outline-to-corpus mapping (coverage matrix)
- Corpus trend analysis from extracted items
- Structured document comparison
- Multi-book synthesis workflows
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.modules.generation.model_router import RewriteModelRouter
from src.modules.orchestration.models import (
    CapabilityTag,
    Tool,
    ToolInputSchema,
    ToolOutputSchema,
    ToolResult,
)
from src.modules.orchestration.tool_registry import register_tool

logger = logging.getLogger(__name__)


def map_outline_to_corpus(input_data: dict[str, Any]) -> ToolResult:
    """Align a reference outline to sections across multiple books via cross-book RAG.

    This is a domain-agnostic tool that works for:
    - Syllabi mapping to textbooks
    - Research protocol mapping to documents
    - Audit checklist mapping to reports
    - Table of requirements mapping to manuals

    Args:
        input_data: Should contain outline_text (the reference outline),
                   book_ids (list of book IDs to map against),
                   and optional user_id for cross-book search.

    Returns:
        ToolResult with coverage matrix: outline topic → {book, chapter, section, confidence} + gaps.
    """
    try:
        from src.modules.rag.service import RagService

        outline_text = input_data.get("outline_text")
        book_ids = input_data.get("book_ids", [])
        user_id = input_data.get("user_id")

        if not outline_text:
            return ToolResult.error_result(
                error="Missing required field: outline_text",
                tool_name="map_outline_to_corpus",
            )

        if not book_ids:
            return ToolResult.error_result(
                error="Missing required field: book_ids",
                tool_name="map_outline_to_corpus",
            )

        # Parse outline into topics (simple line-based parsing)
        outline_lines = [line.strip() for line in outline_text.split("\n") if line.strip()]
        topics = []
        for line in outline_lines:
            # Skip empty lines and numbering
            clean_line = line
            for prefix in ["1.", "2.", "3.", "4.", "5.", "-", "*", "•", "#", "##"]:
                if clean_line.startswith(prefix):
                    clean_line = clean_line[len(prefix):].strip()
            if clean_line:
                topics.append(clean_line)

        if not topics:
            topics = [outline_text]  # Fallback: use entire text as single topic

        # For each topic, search across all books
        rag = RagService()
        router = RewriteModelRouter()
        coverage_matrix = []

        for topic in topics:
            topic_coverage = {
                "topic": topic,
                "books": [],
                "covered": False,
            }

            for book_id in book_ids:
                # Search for topic in this book
                try:
                    results = rag.retrieve(topic, book_id=book_id, sections=[], top_k=3)

                    if results:
                        # Assess confidence based on relevance scores
                        avg_score = sum(r.get("score", 0) for r in results) / len(results)
                        confidence = "high" if avg_score > 0.8 else "medium" if avg_score > 0.5 else "low"

                        best_match = results[0]
                        topic_coverage["books"].append(
                            {
                                "book_id": book_id,
                                "section_id": best_match.get("section_id"),
                                "heading": best_match.get("heading"),
                                "confidence": confidence,
                                "score": avg_score,
                                "excerpt": best_match.get("text", "")[:300],
                            }
                        )
                        topic_coverage["covered"] = True
                except Exception as exc:
                    logger.warning("Search failed for topic %s in book %s: %s", topic, book_id, exc)

            coverage_matrix.append(topic_coverage)

        # Identify gaps
        gaps = [item for item in coverage_matrix if not item["covered"]]

        # Build citations
        citations = []
        for item in coverage_matrix:
            for book in item["books"]:
                citations.append(
                    {
                        "section_id": book.get("section_id"),
                        "heading": book.get("heading"),
                        "book_id": book.get("book_id"),
                    }
                )

        output = {
            "outline_text": outline_text,
            "topics": topics,
            "coverage_matrix": coverage_matrix,
            "total_topics": len(topics),
            "covered_topics": len([c for c in coverage_matrix if c["covered"]]),
            "gaps": gaps,
            "gap_count": len(gaps),
            "coverage_percentage": (len([c for c in coverage_matrix if c["covered"]]) / len(topics)) * 100 if topics else 0,
        }

        return ToolResult.success_result(
            output=output, citations=citations, tool_name="map_outline_to_corpus"
        )

    except Exception as exc:
        logger.exception("map_outline_to_corpus failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="map_outline_to_corpus")


def analyze_corpus_trends(input_data: dict[str, Any]) -> ToolResult:
    """Aggregate extracted items into frequency/weight analysis.

    Takes extracted items (e.g., questions, clauses, cited studies) and
    produces trend analysis: most frequent topics, recurring patterns,
    weight distribution across documents.

    Args:
        input_data: Should contain extracted_items (list of extracted items)
                   and optional analysis_type (frequency, weight, patterns).

    Returns:
        ToolResult with trend analysis and statistics.
    """
    try:
        extracted_items = input_data.get("extracted_items", [])
        analysis_type = input_data.get("analysis_type", "frequency")

        if not extracted_items:
            return ToolResult.error_result(
                error="Missing required field: extracted_items",
                tool_name="analyze_corpus_trends",
            )

        # Frequency analysis
        if analysis_type == "frequency":
            # Count occurrences of each item type or keyword
            frequency_map = {}
            for item in extracted_items:
                if isinstance(item, dict):
                    # Extract key field for counting
                    key = item.get("type", item.get("category", "general"))
                    frequency_map[key] = frequency_map.get(key, 0) + 1

            # Sort by frequency
            sorted_frequencies = sorted(
                [{"item_type": k, "count": v} for k, v in frequency_map.items()],
                key=lambda x: x["count"],
                reverse=True,
            )

            output = {
                "analysis_type": "frequency",
                "total_items": len(extracted_items),
                "frequency_distribution": sorted_frequencies,
                "unique_types": len(frequency_map),
            }

        elif analysis_type == "patterns":
            # Analyze recurring patterns across items
            patterns = []
            for i, item in enumerate(extracted_items):
                if isinstance(item, dict):
                    # Look for common fields
                    fields = list(item.keys())
                    patterns.append(
                        {
                            "item_index": i,
                            "fields": fields,
                            "field_count": len(fields),
                        }
                    )

            # Find most common field combinations
            field_combinations = {}
            for p in patterns:
                combo = tuple(sorted(p["fields"]))
                field_combinations[combo] = field_combinations.get(combo, 0) + 1

            output = {
                "analysis_type": "patterns",
                "total_items": len(extracted_items),
                "common_patterns": sorted(
                    [{"fields": list(k), "count": v} for k, v in field_combinations.items()],
                    key=lambda x: x["count"],
                    reverse=True,
                ),
            }

        else:
            # Default: basic statistics
            output = {
                "analysis_type": "basic",
                "total_items": len(extracted_items),
                "item_types": list(set(type(i).__name__ for i in extracted_items)),
            }

        return ToolResult.success_result(output=output, tool_name="analyze_corpus_trends")

    except Exception as exc:
        logger.exception("analyze_corpus_trends failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="analyze_corpus_trends")


def compare_documents(input_data: dict[str, Any]) -> ToolResult:
    """Structured evidence diff across documents (Elicit-style).

    Compares multiple documents on a specific aspect, retrieving evidence
    from each and presenting a side-by-side comparison.

    Args:
        input_data: Should contain doc_ids (list of document IDs),
                   aspect (the comparison dimension),
                   and optional instruction for synthesis.

    Returns:
        ToolResult with comparison table and evidence per document.
    """
    try:
        from src.modules.generation.model_router import RewriteModelRouter
        from src.modules.rag.service import RagService

        doc_ids = input_data.get("doc_ids", [])
        aspect = input_data.get("aspect")
        instruction = input_data.get("instruction", f"Compare how each document addresses: {aspect}")

        if not doc_ids:
            return ToolResult.error_result(
                error="Missing required field: doc_ids",
                tool_name="compare_documents",
            )

        if not aspect:
            return ToolResult.error_result(
                error="Missing required field: aspect",
                tool_name="compare_documents",
            )

        rag = RagService()
        router = RewriteModelRouter()

        # Retrieve evidence from each document
        document_evidence = []

        for doc_id in doc_ids:
            try:
                results = rag.retrieve(aspect, book_id=doc_id, sections=[], top_k=3)

                if results:
                    evidence_text = "\n\n".join(
                        [f"- {r.get('heading', '')}: {r.get('text', '')[:500]}" for r in results]
                    )

                    document_evidence.append(
                        {
                            "doc_id": doc_id,
                            "evidence": evidence_text,
                            "source_count": len(results),
                            "sources": [
                                {
                                    "section_id": r.get("section_id"),
                                    "heading": r.get("heading"),
                                }
                                for r in results
                            ],
                        }
                    )
                else:
                    document_evidence.append(
                        {
                            "doc_id": doc_id,
                            "evidence": "No relevant evidence found",
                            "source_count": 0,
                            "sources": [],
                        }
                    )
            except Exception as exc:
                logger.warning("Evidence retrieval failed for doc %s: %s", doc_id, exc)
                document_evidence.append(
                    {
                        "doc_id": doc_id,
                        "evidence": f"Error: {str(exc)}",
                        "source_count": 0,
                        "sources": [],
                    }
                )

        # Synthesize comparison
        evidence_summary = "\n\n".join(
            [f"Document {e['doc_id']}:\n{e['evidence']}" for e in document_evidence]
        )

        synthesis_prompt = f"""Compare the following documents on the aspect: {aspect}

Document evidence:
{evidence_summary}

Additional instruction: {instruction}

Provide a structured comparison table highlighting similarities, differences, and unique insights from each document."""

        synthesis = router.generate(
            system_prompt="You are an analytical comparison engine. Provide structured, evidence-based comparisons.",
            user_prompt=synthesis_prompt,
            max_tokens=2000,
        )

        # Build citations
        citations = []
        for e in document_evidence:
            for s in e.get("sources", []):
                citations.append(
                    {
                        "section_id": s.get("section_id"),
                        "heading": s.get("heading"),
                        "doc_id": e.get("doc_id"),
                    }
                )

        output = {
            "aspect": aspect,
            "doc_ids": doc_ids,
            "document_evidence": document_evidence,
            "synthesis": synthesis.get("text", "").strip(),
            "instruction": instruction,
        }

        return ToolResult.success_result(
            output=output, citations=citations, tool_name="compare_documents"
        )

    except Exception as exc:
        logger.exception("compare_documents failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="compare_documents")


def register_corpus_tools() -> None:
    """Register corpus research tools in the global registry."""

    # map_outline_to_corpus
    register_tool(
        Tool(
            name="map_outline_to_corpus",
            description="Align a reference outline to sections across multiple books via cross-book RAG. Returns coverage matrix with gaps.",
            input_schema=ToolInputSchema(
                properties={
                    "outline_text": {"type": "string", "description": "Reference outline text"},
                    "book_ids": {"type": "array", "description": "List of book IDs to map against"},
                    "user_id": {"type": "string", "description": "User ID for cross-book search"},
                },
                required=["outline_text", "book_ids"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "outline_text": {"type": "string"},
                    "topics": {"type": "array"},
                    "coverage_matrix": {"type": "array"},
                    "total_topics": {"type": "integer"},
                    "covered_topics": {"type": "integer"},
                    "gaps": {"type": "array"},
                    "gap_count": {"type": "integer"},
                    "coverage_percentage": {"type": "number"},
                }
            ),
            capability_tags={CapabilityTag.READ, CapabilityTag.ANALYSIS},
            estimated_cost_seconds=10.0,
            executor=map_outline_to_corpus,
        )
    )

    # analyze_corpus_trends
    register_tool(
        Tool(
            name="analyze_corpus_trends",
            description="Aggregate extracted items into frequency/weight analysis. Identifies recurring patterns and topic distribution.",
            input_schema=ToolInputSchema(
                properties={
                    "extracted_items": {"type": "array", "description": "List of extracted items"},
                    "analysis_type": {"type": "string", "description": "Analysis type: frequency, patterns, basic"},
                },
                required=["extracted_items"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "analysis_type": {"type": "string"},
                    "total_items": {"type": "integer"},
                    "frequency_distribution": {"type": "array"},
                    "common_patterns": {"type": "array"},
                }
            ),
            capability_tags={CapabilityTag.READ, CapabilityTag.ANALYSIS},
            estimated_cost_seconds=2.0,
            executor=analyze_corpus_trends,
        )
    )

    # compare_documents
    register_tool(
        Tool(
            name="compare_documents",
            description="Structured evidence diff across documents (Elicit-style). Compares documents on a specific aspect.",
            input_schema=ToolInputSchema(
                properties={
                    "doc_ids": {"type": "array", "description": "List of document IDs to compare"},
                    "aspect": {"type": "string", "description": "Comparison dimension"},
                    "instruction": {"type": "string", "description": "Additional instruction for synthesis"},
                },
                required=["doc_ids", "aspect"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "aspect": {"type": "string"},
                    "doc_ids": {"type": "array"},
                    "document_evidence": {"type": "array"},
                    "synthesis": {"type": "string"},
                }
            ),
            capability_tags={CapabilityTag.READ, CapabilityTag.ANALYSIS},
            estimated_cost_seconds=8.0,
            executor=compare_documents,
        )
    )

    # multi_book_synthesis
    register_tool(
        Tool(
            name="multi_book_synthesis",
            description="Synthesize a merged book from multiple sources following an outline. Per topic: cross-book retrieve → dedup → generate → assemble → export.",
            input_schema=ToolInputSchema(
                properties={
                    "outline_text": {"type": "string", "description": "Outline structure for the merged book"},
                    "book_ids": {"type": "array", "description": "Source book IDs to synthesize from"},
                    "user_id": {"type": "string", "description": "User ID for provenance"},
                    "output_format": {"type": "string", "description": "Output format: docx or markdown"},
                    "title": {"type": "string", "description": "Title for the merged book"},
                },
                required=["outline_text", "book_ids", "user_id"],
            ),
            output_schema=ToolOutputSchema(
                properties={
                    "job_id": {"type": "string"},
                    "status": {"type": "string"},
                    "title": {"type": "string"},
                    "topic_count": {"type": "integer"},
                }
            ),
            capability_tags={CapabilityTag.BATCH, CapabilityTag.WRITE, CapabilityTag.GENERATION},
            estimated_cost_seconds=600.0,  # 10 minutes
            is_write=True,
            is_batch=True,
            executor=multi_book_synthesis,
        )
    )


def multi_book_synthesis(input_data: dict[str, Any]) -> ToolResult:
    """Synthesize a merged book from multiple sources following an outline.

    This is a slow-path batch job that:
    1. Parses the outline into topics
    2. For each topic: cross-book retrieve → deduplicate/conflict-note
    3. Generate content for each topic
    4. Assemble into unified document
    5. Export to DOCX or Markdown

    Args:
        input_data: Should contain outline_text, book_ids, user_id,
                   optional output_format (docx/markdown), and title.

    Returns:
        ToolResult with job_id for tracking.
    """
    try:
        import time
        import uuid

        from src.modules.generation.model_router import RewriteModelRouter
        from src.modules.rag.service import RagService

        outline_text = input_data.get("outline_text")
        book_ids = input_data.get("book_ids", [])
        user_id = input_data.get("user_id")
        output_format = input_data.get("output_format", "docx")
        title = input_data.get("title", "Merged Book")

        if not outline_text:
            return ToolResult.error_result(
                error="Missing required field: outline_text",
                tool_name="multi_book_synthesis",
            )

        if not book_ids:
            return ToolResult.error_result(
                error="Missing required field: book_ids",
                tool_name="multi_book_synthesis",
            )

        # Generate job ID
        job_id = f"synthesis_{uuid.uuid4().hex[:12]}"

        # Store job in batch_tools job store
        from src.modules.orchestration.batch_tools import _job_store

        _job_store[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Multi-book synthesis job queued",
            "book_ids": book_ids,
            "user_id": user_id,
            "outline_text": outline_text,
            "output_format": output_format,
            "title": title,
            "created_at": time.time(),
            "result": None,
            "error": None,
        }

        # In production, this would queue to a worker
        # For synchronous execution (for now):
        try:
            _job_store[job_id]["status"] = "running"
            _job_store[job_id]["progress"] = 10
            _job_store[job_id]["message"] = "Parsing outline..."

            # Parse outline into topics
            outline_lines = [line.strip() for line in outline_text.split("\n") if line.strip()]
            topics = []
            current_section = None

            for line in outline_lines:
                if line.startswith("#") or line.startswith("##"):
                    current_section = line.lstrip("#").strip()
                elif current_section:
                    topics.append({"section": current_section, "topic": line})

            if not topics:
                topics = [{"section": "General", "topic": line} for line in outline_lines]

            _job_store[job_id]["progress"] = 20
            _job_store[job_id]["message"] = f"Processing {len(topics)} topics..."

            rag = RagService()
            router = RewriteModelRouter()

            synthesized_sections = []

            for i, topic_item in enumerate(topics):
                topic = topic_item["topic"]
                section = topic_item["section"]

                # Cross-book retrieval for this topic
                all_chunks = []
                for book_id in book_ids:
                    try:
                        results = rag.retrieve(topic, book_id=book_id, sections=[], top_k=3)
                        all_chunks.extend(results)
                    except Exception:
                        pass

                # Deduplicate chunks
                seen_texts = set()
                unique_chunks = []
                for chunk in all_chunks:
                    text = chunk.get("text", "")[:200]
                    if text not in seen_texts:
                        seen_texts.add(text)
                        unique_chunks.append(chunk)

                # Generate content for this topic
                context = "\n\n".join(
                    [f"- {c.get('heading', '')}: {c.get('text', '')[:500]}" for c in unique_chunks]
                )

                prompt = f"""Write a comprehensive section on: {topic}
Context from sources:
{context}

Section: {section}

Write in a clear, academic style. Synthesize information from all sources. Note any conflicts or differences between sources."""

                result = router.generate(
                    system_prompt="You are an academic synthesizer. Create comprehensive, well-sourced content.",
                    user_prompt=prompt,
                    max_tokens=1500,
                )

                synthesized_sections.append(
                    {
                        "heading": f"## {topic}",
                        "body": result.get("text", "").strip(),
                        "section": section,
                    }
                )

                # Update progress
                progress = 20 + int((i + 1) / len(topics) * 60)
                _job_store[job_id]["progress"] = progress
                _job_store[job_id]["message"] = f"Synthesized {i + 1}/{len(topics)} topics..."

            _job_store[job_id]["progress"] = 80
            _job_store[job_id]["message"] = "Assembling document..."

            # Assemble into unified document
            full_content = f"# {title}\n\n"
            for sec in synthesized_sections:
                full_content += f"{sec['heading']}\n\n{sec['body']}\n\n"

            # Export
            if output_format == "docx":
                from src.modules.orchestration.write_tools import export_docx

                export_result = export_docx(
                    {"content": full_content, "filename": f"{title.replace(' ', '_')}.docx", "title": title}
                )
                artifact_path = export_result.artifact_path
            else:
                from src.modules.orchestration.write_tools import export_markdown

                export_result = export_markdown(
                    {"content": full_content, "filename": f"{title.replace(' ', '_')}.md"}
                )
                artifact_path = export_result.artifact_path

            _job_store[job_id]["status"] = "done"
            _job_store[job_id]["progress"] = 100
            _job_store[job_id]["message"] = "Multi-book synthesis complete"
            _job_store[job_id]["artifact_path"] = artifact_path
            _job_store[job_id]["result"] = {
                "title": title,
                "topic_count": len(topics),
                "output_format": output_format,
            }

            logger.info("Multi-book synthesis complete: %s", job_id)

        except Exception as exc:
            _job_store[job_id]["status"] = "error"
            _job_store[job_id]["error"] = str(exc)
            _job_store[job_id]["message"] = "Multi-book synthesis failed"
            logger.exception("Multi-book synthesis failed: %s", exc)

        output = {
            "job_id": job_id,
            "status": _job_store[job_id]["status"],
            "message": _job_store[job_id]["message"],
            "title": title,
            "topic_count": len(topics),
        }

        return ToolResult.success_result(
            output=output, job_id=job_id, artifact_path=_job_store[job_id].get("artifact_path"), tool_name="multi_book_synthesis"
        )

    except Exception as exc:
        logger.exception("multi_book_synthesis failed: %s", exc)
        return ToolResult.error_result(error=str(exc), tool_name="multi_book_synthesis")


# Auto-register on import
register_corpus_tools()

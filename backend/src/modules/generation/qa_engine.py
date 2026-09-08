"""Book-grounded Q&A with subject-domain guard for scenario questions."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from src.modules.generation.model_router import RewriteModelRouter
from src.modules.generation.rewrite_validation import normalize_heading

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(normalize_heading(text or "").lower()) if len(t) > 2}


def retrieve_sections(
    sections: Sequence[Dict[str, Any]],
    query: str,
    *,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Lexical retrieval over heading + body (no vector index required)."""
    q = _tokens(query)
    if not q:
        return list(sections[:top_k])

    scored: List[tuple[float, Dict[str, Any]]] = []
    for sec in sections:
        heading = str(sec.get("heading") or "")
        body = str(sec.get("text") or "")[:4000]
        h_tok = _tokens(heading)
        b_tok = _tokens(body)
        score = len(q & h_tok) * 4.0 + len(q & b_tok) * 1.0
        if any(w in heading.lower() for w in query.lower().split() if len(w) > 3):
            score += 2.0
        if score > 0:
            scored.append((score, sec))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("heading") or "")))
    if scored:
        return [s for _, s in scored[:top_k]]
    return list(sections[:top_k])


def _format_context(chunks: Sequence[Dict[str, Any]], *, max_chars: int = 12000) -> tuple[str, List[str]]:
    from src.modules.rag.context_builder import build_qa_context

    return build_qa_context(chunks, max_chars=max_chars, include_citations=True)


def _chunk_context_by_sections(chunks: Sequence[Dict[str, Any]], *, max_chars_per_chunk: int = 4000) -> List[Dict[str, Any]]:
    """Split retrieved chunks into logical section-based groups for processing."""
    if not chunks:
        return []
    
    # Group chunks by section/heading
    section_groups = {}
    for chunk in chunks:
        section_id = chunk.get("section_id") or chunk.get("heading") or "unknown"
        if section_id not in section_groups:
            section_groups[section_id] = []
        section_groups[section_id].append(chunk)
    
    # Build chunks with character limits
    grouped_chunks = []
    current_group = []
    current_chars = 0
    
    for section_id, section_chunks in section_groups.items():
        section_text = " ".join([str(c.get("text") or "") for c in section_chunks])
        section_chars = len(section_text)
        
        if current_chars + section_chars > max_chars_per_chunk and current_group:
            # Save current group and start new one
            grouped_chunks.append({
                "chunks": current_group,
                "text": " ".join([str(c.get("text") or "") for c in current_group]),
                "headings": list(set([c.get("heading") for c in current_group if c.get("heading")]))
            })
            current_group = section_chunks
            current_chars = section_chars
        else:
            current_group.extend(section_chunks)
            current_chars += section_chars
    
    # Add final group
    if current_group:
        grouped_chunks.append({
            "chunks": current_group,
            "text": " ".join([str(c.get("text") or "") for c in current_group]),
            "headings": list(set([c.get("heading") for c in current_group if c.get("heading")]))
        })
    
    return grouped_chunks


def _fallback_subject_relevance(
    question: str,
    *,
    subject_hint: str,
    book_title: str,
) -> tuple[bool, str]:
    """When the relevance LLM returns unparseable output, use book-domain token overlap."""
    domain = _tokens(subject_hint) | _tokens(book_title)
    overlap = _tokens(question) & domain
    if overlap:
        return True, "keyword overlap with book domain"
    # User is asking about their uploaded book — prefer answering unless clearly off-topic.
    return True, "classification unavailable — assume related to uploaded book"


def _parse_json_bool(raw: str) -> Optional[bool]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "related" in data:
            return bool(data["related"])
    except json.JSONDecodeError:
        pass
    low = text.lower()
    if "true" in low and "false" not in low:
        return True
    if "false" in low and "true" not in low:
        return False
    return None


class BookQaEngine:
    """Answer questions using ingested book sections + optional domain reasoning."""

    def __init__(self, *, book_title: str, subject_hint: str = "", book_id: str = "") -> None:
        self.book_title = (book_title or "Book").strip()
        self.subject_hint = (subject_hint or book_title or "this subject").strip()
        self.book_id = (book_id or "").strip()
        self.router = RewriteModelRouter()

    def check_subject_relevance(self, question: str) -> tuple[bool, str]:
        system = (
            "You classify whether a user question belongs to the same academic subject as a given book. "
            "Reply with JSON only: {\"related\": true|false, \"reason\": \"...\"}"
        )
        user = (
            f"Book title: {self.book_title}\n"
            f"Subject domain: {self.subject_hint}\n"
            f"Question: {question}\n"
            "Is the question related to this subject domain?"
        )
        raw = self.router.generate(system_prompt=system, user_prompt=user, max_tokens=200).get("text") or ""
        related = _parse_json_bool(raw)
        if related is None:
            return _fallback_subject_relevance(
                question,
                subject_hint=self.subject_hint,
                book_title=self.book_title,
            )
        reason = ""
        try:
            reason = str(json.loads(raw).get("reason") or "")
        except Exception:
            reason = raw[:120]
        return related, reason

    def _answer_multistep(
        self,
        question: str,
        sections: Sequence[Dict[str, Any]],
        *,
        allow_external: bool = True,
        depth: str = "medium",
        language_level: str = "simple",
        format_type: str = "paragraph",
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        """Multi-step CoT path: decompose → retrieve per sub-Q → synthesize."""
        from src.modules.generation.qa_reasoning import (
            ReasoningAnswer,
            decompose_question,
            retrieve_for_sub_questions,
            synthesize_answer,
        )

        rag = None
        if self.book_id:
            try:
                from src.modules.rag.service import RagService
                rag = RagService()
            except Exception:
                rag = None

        from src import config as cfg

        top_k = int(getattr(cfg, "QA_MULTISTEP_TOP_K_PER_Q", 3) or 3)
        cross_book_enabled = bool(getattr(cfg, "RAG_CORPUS_INDEX_ENABLED", False))
        sub_qs = decompose_question(question, self.router)
        merged = retrieve_for_sub_questions(
            sub_qs,
            rag,
            book_id=self.book_id or None,
            cross_book=cross_book_enabled,
            top_k_per_question=top_k,
        )
        # Supplement with lexical retrieval when RAG is unavailable
        if not merged:
            merged = retrieve_sections(sections, question, top_k=top_k * len(sub_qs))

        result: ReasoningAnswer = synthesize_answer(question, sub_qs, merged, self.router, conversation_history=conversation_history or [])
        return {
            "answer": result.answer,
            "reasoning": result.reasoning,
            "refused": False,
            "related": True,
            "sources": result.sources,
            "sub_questions": result.sub_questions,
            "hops": result.hops,
            "retrieval": "multistep_cot",
        }

    def _answer_singleshot(
        self,
        question: str,
        sections: Sequence[Dict[str, Any]],
        *,
        allow_external: bool = True,
        depth: str = "medium",
        language_level: str = "simple",
        format_type: str = "paragraph",
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        """Existing single-retrieval + single-LLM-call path (unchanged logic)."""
        relevant = self._retrieve(question, sections)
        from src import config as cfg

        max_ctx = int(getattr(cfg, "RAG_CONTEXT_MAX_CHARS", 12000) or 12000)
        context, citation_labels = _format_context(relevant, max_chars=max_ctx)
        
        # Check if context is too large for single processing
        context_length = len(context)
        chunk_threshold = 6000  # Use chunked processing if context exceeds this

        related, rel_reason = self.check_subject_relevance(question)
        if not related and not allow_external:
            return {
                "answer": (
                    f"This question does not appear related to **{self.book_title}** "
                    f"({self.subject_hint}). I can only answer questions within this book's subject."
                ),
                "refused": True,
                "related": False,
                "sources": citation_labels[:3] or [str(s.get("heading") or "") for s in relevant[:3]],
            }

        # Use chunked processing for large contexts
        if context_length > chunk_threshold:
            return self._answer_with_chunks(
                question, relevant, depth, language_level, format_type, related, citation_labels
            )

        simple = language_level == "simple"
        bullets = format_type == "bullet" or format_type == "exam_oriented"
        short = depth in {"very_short", "short"}

        system_parts = [
            f"You are a helpful tutor for the book: {self.book_title}.",
            f"Subject domain: {self.subject_hint}.",
        ]
        if related:
            system_parts.append(
                "Use the provided book excerpts as primary grounding. "
                "For scenario questions not literally in the book, apply principles from the excerpts "
                "and standard subject knowledge — do not invent facts, citations, or examples not implied by context."
            )
        else:
            system_parts.append(
                "The question is outside the book's core domain. Give a brief general answer only if clearly unrelated "
                "fields are not involved; prefer refusing if unsure."
            )
        if simple:
            system_parts.append("Use very simple English.")
        if short:
            system_parts.append("Keep the answer short and exam-focused.")
        if bullets:
            system_parts.append("Use markdown bullets where helpful.")
        system_parts.append("Do not mention that you are an AI. Cite section headings when useful.")

        user_parts = [
            f"Question:\n{question}\n",
            f"Book excerpts:\n{context or '(no matching excerpts — use subject knowledge carefully)'}\n",
        ]
        
        # Add conversation history if available
        if conversation_history and len(conversation_history) > 0:
            history_text = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}" 
                for msg in conversation_history[-6:]  # Last 6 exchanges
            ])
            user_parts.append(f"Previous conversation:\n{history_text}\n")
            user_parts.append("NOTE: Consider the previous conversation to avoid repeating answers. If the user asks a similar question, provide a concise reference to previous answers rather than repeating the full response.")
        
        user_parts.append("Write a clear answer.")

        text = self.router.generate(
            system_prompt="\n".join(system_parts),
            user_prompt="\n".join(user_parts),
            max_tokens=2000 if short else 3000,
        ).get("text") or ""

        if not text.strip():
            return {
                "answer": "[!] No answer generated (check LLM provider / API keys).",
                "refused": False,
                "related": related,
                "sources": citation_labels[:5] or [str(s.get("heading") or "") for s in relevant[:5]],
            }

        return {
            "answer": text.strip(),
            "refused": False,
            "related": related,
            "rel_reason": rel_reason,
            "sources": citation_labels[:5] or [str(s.get("heading") or "") for s in relevant[:5]],
            "retrieval": "vector_rag_rerank" if self.book_id else "lexical",
        }

    def _answer_with_chunks(
        self,
        question: str,
        relevant: Sequence[Dict[str, Any]],
        depth: str,
        language_level: str,
        format_type: str,
        related: bool,
        citation_labels: List[str],
    ) -> Dict[str, Any]:
        """Process large context in chunks and synthesize comprehensive answer."""
        # Chunk the context logically by sections
        context_chunks = _chunk_context_by_sections(relevant, max_chars_per_chunk=4000)
        
        if not context_chunks:
            return {
                "answer": "[!] No context chunks generated.",
                "refused": False,
                "related": related,
                "sources": citation_labels[:5],
                "retrieval": "chunked",
            }
        
        simple = language_level == "simple"
        bullets = format_type == "bullet" or format_type == "exam_oriented"
        short = depth in {"very_short", "short"}
        
        # Generate partial answers for each chunk
        partial_answers = []
        all_sources = set(citation_labels)
        
        for i, chunk in enumerate(context_chunks):
            chunk_context = chunk["text"]
            chunk_headings = chunk.get("headings", [])
            
            system_parts = [
                f"You are a helpful tutor for the book: {self.book_title}.",
                f"Subject domain: {self.subject_hint}.",
            ]
            if related:
                system_parts.append(
                    "Use the provided book excerpts as primary grounding. "
                    "Focus on the specific sections provided in this chunk."
                )
            if simple:
                system_parts.append("Use very simple English.")
            if bullets:
                system_parts.append("Use markdown bullets where helpful.")
            system_parts.append("Do not mention that you are an AI. Cite section headings when useful.")
            
            user_parts = [
                f"Question: {question}\n",
                f"Book excerpts (Part {i+1}/{len(context_chunks)}):\n{chunk_context}\n",
                f"Relevant sections: {', '.join(chunk_headings[:3])}\n",
                "Write a focused answer based on this chunk only.",
            ]
            
            chunk_answer = self.router.generate(
                system_prompt="\n".join(system_parts),
                user_prompt="\n".join(user_parts),
                max_tokens=1500,
            ).get("text") or ""
            
            if chunk_answer.strip():
                partial_answers.append(chunk_answer)
                # Collect sources from this chunk
                chunk_sources = [str(c.get("heading") or "") for c in chunk["chunks"] if c.get("heading")]
                all_sources.update(chunk_sources)
        
        # Synthesize final answer from partial answers
        if partial_answers:
            synthesis_system = [
                f"You are synthesizing answers about: {self.book_title}.",
                f"Subject domain: {self.subject_hint}.",
                "Combine the following partial answers into a coherent, comprehensive answer.",
                "Remove duplicates and ensure logical flow.",
            ]
            if simple:
                synthesis_system.append("Use very simple English.")
            if bullets:
                synthesis_system.append("Use markdown bullets where helpful.")
            
            combined_partial = "\n\n".join([f"Partial Answer {i+1}:\n{ans}" for i, ans in enumerate(partial_answers)])
            
            synthesis_user = [
                f"Question: {question}\n",
                f"Partial answers to synthesize:\n{combined_partial}\n",
                "Create a comprehensive, well-structured answer.",
            ]
            
            final_answer = self.router.generate(
                system_prompt="\n".join(synthesis_system),
                user_prompt="\n".join(synthesis_user),
                max_tokens=3000,
            ).get("text") or ""
            
            return {
                "answer": final_answer,
                "refused": False,
                "related": related,
                "sources": list(all_sources)[:10],
                "retrieval": "chunked",
                "chunks_processed": len(context_chunks),
            }
        
        return {
            "answer": "[!] No partial answers generated from chunks.",
            "refused": False,
            "related": related,
            "sources": list(all_sources)[:5],
            "retrieval": "chunked",
        }

    def answer(
        self,
        question: str,
        sections: Sequence[Dict[str, Any]],
        *,
        allow_external: bool = True,
        depth: str = "medium",
        language_level: str = "simple",
        format_type: str = "paragraph",
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        """Answer a question. Routes to multi-step CoT or single-shot depending on config."""
        from src import config as cfg

        _multistep_enabled = bool(int(getattr(cfg, "QA_MULTISTEP_ENABLED", 0) or 0))
        _long_enough = len(question.split()) >= 6
        if _multistep_enabled and _long_enough:
            return self._answer_multistep(
                question,
                sections,
                allow_external=allow_external,
                depth=depth,
                conversation_history=conversation_history or [],
            )
        else:
            return self._answer_single_shot(
                question,
                sections,
                allow_external=allow_external,
                depth=depth,
                language_level=language_level,
                format_type=format_type,
                conversation_history=conversation_history or [],
            )

    def _retrieve(self, question: str, sections: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from src import config
        from pathlib import Path

        # Use knowledge graph-augmented retrieval when enabled
        if self.book_id and getattr(config, "KNOWLEDGE_GRAPH_ENABLED", False):
            try:
                from src.modules.rag.service import RagService
                from src.modules.knowledge.graph_retriever import retrieve_with_graph

                rag = RagService()
                db_path = Path(getattr(config, "KNOWLEDGE_DB_PATH", "output/knowledge_base.db"))
                top_k = int(getattr(config, "RAG_TOP_K", 6) or 6)

                graph_hits = retrieve_with_graph(
                    question,
                    rag,
                    db_path=db_path,
                    book_id=self.book_id,
                    top_k_chunks=top_k,
                )
                if graph_hits:
                    return graph_hits
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Graph retrieval failed, falling back to RAG: %s", exc)

        # Standard RAG retrieval
        if self.book_id and getattr(config, "RAG_ENABLED", True):
            try:
                from src.modules.rag.service import RagService

                hits = RagService().retrieve(
                    question,
                    book_id=self.book_id,
                    sections=sections,
                    top_k=int(getattr(config, "RAG_TOP_K", 6) or 6),
                )
                if hits:
                    return hits
            except Exception:
                pass
        return retrieve_sections(sections, question, top_k=6)

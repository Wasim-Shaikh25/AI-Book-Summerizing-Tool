"""Multi-step chain-of-thought Q&A reasoning module.

Provides question decomposition, per-sub-question retrieval, and structured
synthesis. Imported by ``BookQaEngine._answer_multistep`` when
``QA_MULTISTEP_ENABLED=1``.

No changes to any export, structure, or ingestion modules.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReasoningAnswer:
    """Result of a multi-step CoT reasoning pass."""

    question: str
    reasoning: str          # chain-of-thought written by the synthesis call
    answer: str             # final answer paragraph(s)
    sources: list[dict]     # each entry: {section_id, heading, book_title, excerpt}
    sub_questions: list[str]
    hops: int               # == len(sub_questions)


def decompose_question(question: str, chat: Any) -> list[str]:
    """Break the question into 2–3 focused sub-questions via a lightweight LLM call.

    Failure contract:
    - JSON parse fails → return [question]
    - Result is not a list → return [question]
    - Result list is empty → return [question]
    - Result list length > 3 → return first 3 items only
    - Any exception → return [question], log warning
    """
    system = (
        "Break the following question into 2-3 specific sub-questions that, "
        "when answered together, fully address the original. "
        "Return ONLY a JSON array of strings. No prose."
    )
    try:
        raw = (chat.generate(system_prompt=system, user_prompt=question, max_tokens=200) or {})
        text = (raw.get("text") if isinstance(raw, dict) else str(raw) or "").strip()
        parsed = json.loads(text)
        if not isinstance(parsed, list) or not parsed:
            return [question]
        items = [str(s) for s in parsed if str(s).strip()]
        if not items:
            return [question]
        return items[:3]
    except Exception as exc:
        logger.warning("decompose_question failed (%s) — falling back to raw question", exc)
        return [question]


def retrieve_for_sub_questions(
    sub_questions: list[str],
    rag_service: Any,
    *,
    book_id: str | None = None,
    cross_book: bool = False,
    user_id: str | None = None,
    top_k_per_question: int = 3,
) -> list[dict]:
    """Retrieve separately for each sub-question and deduplicate by chunk_id.

    Returns merged list ordered: first seen wins (preserves retrieval rank of the
    most relevant sub-question's results).
    """
    seen_ids: set[str] = set()
    merged: list[dict] = []

    for sub_q in sub_questions:
        try:
            if rag_service is not None:
                chunks = []
                if cross_book and user_id:
                    # Use cross-book corpus retrieval when enabled and user known
                    chunks = rag_service.retrieve_cross_book(
                        sub_q,
                        user_id,
                        book_ids=[book_id] if book_id else None,
                        top_k=top_k_per_question,
                    ) or []
                if not chunks:
                    chunks = rag_service.retrieve(
                        sub_q,
                        book_id=book_id,
                        top_k=top_k_per_question,
                    ) or []
            else:
                chunks = []
        except Exception as exc:
            logger.warning("retrieve_for_sub_questions: retrieval failed for %r: %s", sub_q, exc)
            chunks = []

        for chunk in chunks:
            cid = str(chunk.get("chunk_id") or chunk.get("section_id") or id(chunk))
            if cid not in seen_ids:
                seen_ids.add(cid)
                merged.append(chunk)

    return merged


def synthesize_answer(
    question: str,
    sub_questions: list[str],
    merged_context: list[dict],
    chat: Any,
    conversation_history: list[dict] | None = None,
) -> ReasoningAnswer:
    """One structured synthesis LLM call combining sub-question context.

    Failure contract:
    - JSON parse fails → ReasoningAnswer(reasoning='', answer=raw_text, sources=[], ...)
    - 'answer' key absent → ReasoningAnswer(reasoning='', answer='', sources=[], ...)
    - merged_context is empty → answer field says 'no information found'; no exception
    """
    ctx_parts: list[str] = []
    if merged_context:
        for i, chunk in enumerate(merged_context, start=1):
            heading = chunk.get("heading") or chunk.get("section_id") or f"Source {i}"
            excerpt = chunk.get("excerpt") or chunk.get("text") or ""
            ctx_parts.append(f"[{i}] {heading}:\n{excerpt[:800]}")
    ctx_block = "\n\n".join(ctx_parts) if ctx_parts else "(no excerpts available)"

    sub_q_block = "\n".join(f"  - {q}" for q in sub_questions) if sub_questions else ""
    user = (
        f"Original question: {question}\n\n"
        + (f"Sub-questions used for retrieval:\n{sub_q_block}\n\n" if sub_q_block else "")
        + f"Book excerpts:\n{ctx_block}"
    )
    
    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        history_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}" 
            for msg in conversation_history[-6:]  # Last 6 exchanges
        ])
        user += f"\n\nPrevious conversation:\n{history_text}\n"
        user += "NOTE: Consider the previous conversation to avoid repeating answers. If the user asks a similar question, provide a concise reference to previous answers rather than repeating the full response."

    system = (
        "You are a precise academic tutor. Answer using ONLY the provided excerpts. "
        "Show your reasoning step by step before giving the final answer. "
        "If the context does not contain enough information, say so explicitly — "
        "do not invent facts.\n"
        "Reply with JSON matching this schema:\n"
        '{"reasoning": "<step-by-step chain of thought>", '
        '"answer": "<final answer>", '
        '"sources": [{"section_id": "...", "heading": "...", "excerpt": "..."}]}'
    )

    try:
        raw = (chat.generate(system_prompt=system, user_prompt=user, max_tokens=1400) or {})
        text = (raw.get("text") if isinstance(raw, dict) else str(raw) or "").strip()
        parsed = json.loads(text)
        reasoning = str(parsed.get("reasoning") or "")
        answer = str(parsed.get("answer") or "")
        sources = parsed.get("sources") or []
        if not isinstance(sources, list):
            sources = []
    except json.JSONDecodeError:
        reasoning = ""
        answer = (raw.get("text") if isinstance(raw, dict) else str(raw)) or ""
        sources = []
    except Exception as exc:
        logger.warning("synthesize_answer failed (%s)", exc)
        reasoning = ""
        answer = ""
        sources = []

    return ReasoningAnswer(
        question=question,
        reasoning=reasoning,
        answer=answer,
        sources=sources,
        sub_questions=list(sub_questions),
        hops=len(sub_questions),
    )

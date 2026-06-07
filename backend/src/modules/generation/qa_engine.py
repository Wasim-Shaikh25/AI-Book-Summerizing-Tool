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


def _format_context(chunks: Sequence[Dict[str, Any]], *, max_chars: int = 12000) -> str:
    parts: List[str] = []
    used = 0
    for sec in chunks:
        heading = str(sec.get("heading") or "Section").strip()
        body = str(sec.get("text") or "").strip()
        if not body:
            continue
        block = f"### {heading}\n{body[:3000]}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


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
            # Conservative default for legal/scenario phrasing
            tortish = any(
                w in question.lower()
                for w in (
                    "tort",
                    "negligence",
                    "liability",
                    "damages",
                    "injury",
                    "defendant",
                    "plaintiff",
                    "accident",
                    "consumer",
                )
            )
            return tortish, "keyword fallback"
        reason = ""
        try:
            reason = str(json.loads(raw).get("reason") or "")
        except Exception:
            reason = raw[:120]
        return related, reason

    def answer(
        self,
        question: str,
        sections: Sequence[Dict[str, Any]],
        *,
        allow_external: bool = True,
        depth: str = "medium",
        language_level: str = "simple",
        format_type: str = "paragraph",
    ) -> Dict[str, Any]:
        relevant = self._retrieve(question, sections)
        context = _format_context(relevant)

        related, rel_reason = self.check_subject_relevance(question)
        if not related and not allow_external:
            return {
                "answer": (
                    f"This question does not appear related to **{self.book_title}** "
                    f"({self.subject_hint}). I can only answer questions within this book's subject."
                ),
                "refused": True,
                "related": False,
                "sources": [str(s.get("heading") or "") for s in relevant[:3]],
            }

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
                "and standard subject knowledge — do not invent case names or statutes not implied by context."
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
            "Write a clear answer.",
        ]

        text = self.router.generate(
            system_prompt="\n".join(system_parts),
            user_prompt="\n".join(user_parts),
            max_tokens=900 if short else 1400,
        ).get("text") or ""

        if not text.strip():
            return {
                "answer": "[!] No answer generated (check LLM provider / API keys).",
                "refused": False,
                "related": related,
                "sources": [str(s.get("heading") or "") for s in relevant[:5]],
            }

        return {
            "answer": text.strip(),
            "refused": False,
            "related": related,
            "rel_reason": rel_reason,
            "sources": [str(s.get("heading") or "") for s in relevant[:5]],
            "retrieval": "vector_rag" if self.book_id else "lexical",
        }

    def _retrieve(self, question: str, sections: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from src import config

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

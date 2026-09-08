"""Book-grounded Q&A handler."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src import config
from src.modules.generation.qa_engine import BookQaEngine
from src.modules.interaction.command_parser import IntentResult
from src.modules.storage.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class AskHandler:
    """Answer topic questions and scenario-based questions using ingested book content."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        book_id: str,
        book_title: str,
        pdf_path: Optional[str] = None,
        ultimate_log_dir: Optional[str] = None,
        subject_hint: str = "",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> None:
        self.store = store
        self.book_id = book_id
        self.book_title = book_title
        self.pdf_path = pdf_path
        self.ultimate_log_dir = ultimate_log_dir
        self.subject_hint = subject_hint or book_title
        self.conversation_history = conversation_history or []

    def _load_sections(self):
        from services.rag_index_helper import load_book_sections

        lines = None
        if self.pdf_path and not self.ultimate_log_dir:
            from src.modules.ingestion.pdf_extractor import extract_pdf

            lines, _, _ = extract_pdf(self.pdf_path)

        return load_book_sections(
            self.store,
            book_id=self.book_id,
            pdf_path=self.pdf_path,
            log_dir=self.ultimate_log_dir,
            lines=lines,
        )

    def _ensure_rag_index(self, sections) -> None:
        if not getattr(config, "RAG_ENABLED", True):
            return
        try:
            from services.rag_index_helper import ensure_rag_index_for_book

            chunks = ensure_rag_index_for_book(
                self.store,
                book_id=self.book_id,
                pdf_path=self.pdf_path,
                log_dir=self.ultimate_log_dir,
            )
            if chunks:
                logger.info("Lazy RAG index ready for book_id=%s chunks=%d", self.book_id, chunks)
        except Exception as exc:
            logger.warning("Lazy RAG ensure skipped: %s", exc)

    def handle_intent(self, intent: IntentResult) -> str | None:
        from src.modules.interaction.command_parser import effective_user_instruction

        question = effective_user_instruction(intent)
        if not question:
            print("[!] Empty question.")
            return None

        sections = self._load_sections()
        if not sections:
            print("[!] No book sections found. Ingest the PDF first.")
            return None

        self._ensure_rag_index(sections)

        engine = BookQaEngine(book_title=self.book_title, subject_hint=self.subject_hint, book_id=self.book_id)
        result = engine.answer(
            question,
            sections,
            allow_external=intent.allow_external_knowledge,
            depth=intent.depth,
            language_level=intent.language_level,
            format_type=intent.format_type,
            conversation_history=self.conversation_history,
        )

        print("\n" + "=" * 60)
        print(f" Q&A — {self.book_title} ")
        print("=" * 60)
        if result.get("sources"):
            print("Sources:", ", ".join(result["sources"][:5]))
        if result.get("related") is False:
            print("(Subject relevance: outside book domain)")
        print()
        print(result.get("answer") or "")
        print("=" * 60 + "\n")
        return {
            "answer": result.get("answer") or "",
            "sources": result.get("sources", []),
            "related": result.get("related", True),
            "retrieval_mode": result.get("retrieval_mode"),
            "reasoning": result.get("reasoning"),
        }

    def handle(self, question: str) -> str | None:
        from src.modules.interaction.command_parser import IntentResult

        intent = IntentResult(
            task_type="question_answer",
            scope="single_question",
            depth="medium",
            language_level="simple",
            format_type="paragraph",
            allow_external_knowledge=True,
            normalized_query=question,
        )
        return self.handle_intent(intent)

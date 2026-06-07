"""Book-grounded Q&A handler."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.modules.generation.qa_engine import BookQaEngine
from src.modules.generation.toc_sections import load_rewrite_sections
from src.modules.ingestion.pdf_extractor import extract_pdf
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
    ) -> None:
        self.store = store
        self.book_id = book_id
        self.book_title = book_title
        self.pdf_path = pdf_path
        self.ultimate_log_dir = ultimate_log_dir
        self.subject_hint = subject_hint or book_title

    def _load_sections(self):
        lines = None
        ultimate_path = None
        hierarchy_path = None
        if self.pdf_path:
            lines, _, _ = extract_pdf(self.pdf_path)
        if self.ultimate_log_dir:
            log_dir = Path(self.ultimate_log_dir)
            ultimate_path = log_dir / "15d_ultimate_sections.json"
            h15f = log_dir / "15f_heading_cleanup.json"
            h15e = log_dir / "15e_chapter_hierarchy.json"
            hierarchy_path = h15f if h15f.exists() else h15e

        return load_rewrite_sections(
            self.store,
            book_id=self.book_id,
            pdf_path=self.pdf_path,
            ultimate_sections_path=ultimate_path,
            chapter_hierarchy_path=hierarchy_path if hierarchy_path and hierarchy_path.exists() else None,
            lines=lines,
            prefer_15e=True,
            prefer_15d=True,
        )

    def handle_intent(self, intent: IntentResult) -> str | None:
        question = (intent.normalized_query or "").strip()
        if not question:
            print("[!] Empty question.")
            return None

        sections = self._load_sections()
        if not sections:
            print("[!] No book sections found. Ingest the PDF first.")
            return None

        engine = BookQaEngine(book_title=self.book_title, subject_hint=self.subject_hint, book_id=self.book_id)
        result = engine.answer(
            question,
            sections,
            allow_external=intent.allow_external_knowledge,
            depth=intent.depth,
            language_level=intent.language_level,
            format_type=intent.format_type,
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
        return result.get("answer")

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

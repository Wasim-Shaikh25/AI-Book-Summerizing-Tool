"""Chat orchestration: intent routing, responses, Word export."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from src import config
from src.modules.export.word_exporter import WordExporter
from src.modules.interaction.command_parser import CommandParser, IntentResult
from src.modules.interaction.handlers.ask_handler import AskHandler
from src.modules.interaction.handlers.rewrite_handler import RewriteHandler
from src.modules.storage.knowledge_store import KnowledgeStore

from auth.config import get_auth_settings
from services.export_policy import resolve_export_mode, user_requests_word_export
from services.title_service import generate_conversation_title
from storage.user_repository import (
    ConversationRepository,
    ExportRepository,
    MessageRepository,
    UserBookRepository,
)

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self) -> None:
        self.store = KnowledgeStore()
        self.parser = CommandParser()
        self.conversations = ConversationRepository()
        self.messages = MessageRepository()
        self.user_books = UserBookRepository()
        self.exports = ExportRepository()
        self.word_exporter = WordExporter(output_folder=config.OUTPUT_FOLDER)

    def _book_context(self, user_id: str, book_id: str) -> dict[str, Any] | None:
        ub = self.user_books.get(user_id, book_id)
        if not ub:
            return None
        conn = self.store.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT title FROM books WHERE book_id = ?", (book_id,))
        row = cur.fetchone()
        conn.close()
        title = row[0] if row else "Book"
        return {
            "book_id": book_id,
            "title": title,
            "file_path": ub["file_path"],
            "log_dir": ub.get("log_dir"),
        }

    def _export_answer_docx(self, user_id: str, content: str, title: str) -> tuple[str, str]:
        export_dir = Path("output/exports") / user_id
        export_dir.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_") or "Notes"
        file_name = f"{safe_title}.docx"
        file_path = export_dir / file_name

        book_data = self.word_exporter.assemble_full_book_structured_text([content], title)
        saved = self.word_exporter.structured_text_to_word(
            book_data, str(file_path), include_toc=False
        )
        record = self.exports.save(user_id, saved, file_name)
        return record.export_id, saved

    def _run_rewrite(self, ctx: dict[str, Any], intent: IntentResult) -> dict[str, Any]:
        import os as _os

        exam = intent.format_type == "exam_oriented" or intent.task_type in ("study_notes", "revision_notes")
        _os.environ["EXAM_ORIENTED"] = "1" if exam else "0"
        compact = intent.depth == "very_short" or intent.task_type == "revision_notes"
        _os.environ["COMPACT_EXAM"] = "1" if compact else "0"

        handler = RewriteHandler(
            self.store,
            book_id=ctx["book_id"],
            book_title=ctx["title"],
            pdf_path=ctx.get("file_path"),
            ultimate_log_dir=ctx.get("log_dir"),
        )

        if intent.scope != "full_book":
            return {"content": "Full-book rewrite is required for this action.", "docx_path": None}

        lines = None
        ultimate_path = None
        hierarchy_path = None
        if ctx.get("file_path"):
            from src.modules.ingestion.pdf_extractor import extract_pdf

            lines, _, _ = extract_pdf(ctx["file_path"])
        if ctx.get("log_dir"):
            log_dir = Path(ctx["log_dir"])
            ultimate_path = log_dir / "15d_ultimate_sections.json"
            h15f = log_dir / "15f_heading_cleanup.json"
            h15e = log_dir / "15e_chapter_hierarchy.json"
            hierarchy_path = h15f if h15f.exists() else h15e

        results = handler.engine.run(
            user_instruction=intent.normalized_query,
            export_to_word=True,
            pdf_path=ctx.get("file_path"),
            ultimate_sections_path=ultimate_path,
            chapter_hierarchy_path=hierarchy_path if hierarchy_path and hierarchy_path.exists() else None,
            lines=lines,
        )
        if "error" in results:
            return {"content": f"Rewrite failed: {results['error']}", "docx_path": None}

        content = results.get("markdown") or "Rewrite completed."
        docx_path = results.get("docx")
        return {"content": content, "docx_path": docx_path, "task": "rewrite"}

    def _run_qa(self, ctx: dict[str, Any], intent: IntentResult) -> dict[str, Any]:
        subject = ctx["title"]
        if "tort" in subject.lower():
            subject = "Law of Torts, negligence, liability, and consumer protection"

        answer = AskHandler(
            self.store,
            book_id=ctx["book_id"],
            book_title=ctx["title"],
            pdf_path=ctx.get("file_path"),
            ultimate_log_dir=ctx.get("log_dir"),
            subject_hint=subject,
        ).handle_intent(intent)

        return {"content": answer or "I could not generate an answer.", "task": "qa"}

    def _handle_word_only_request(
        self, user_id: str, conversation_id: str, ctx: dict[str, Any]
    ) -> dict[str, Any]:
        last = self.messages.get_last_assistant(conversation_id)
        if not last or not last.content.strip():
            return {
                "content": "There is no previous answer to export. Ask a question or request a rewrite first.",
                "docx_available": False,
            }
        export_id, _ = self._export_answer_docx(user_id, last.content, ctx["title"])
        download_url = f"/api/exports/{export_id}"
        meta = {**last.metadata, "docx_available": True, "docx_download_url": download_url, "export_reason": "user_request"}
        assistant = self.messages.add(
            conversation_id,
            "assistant",
            f"Your Word file is ready.\n\nDownload: {download_url}",
            export_id=export_id,
            metadata=meta,
        )
        return {
            "assistant_message": self._msg_to_dict(assistant, download_url),
            "docx_available": True,
            "docx_download_url": download_url,
        }

    def _msg_to_dict(self, msg, download_url: str | None = None) -> dict[str, Any]:
        meta = dict(msg.metadata)
        if download_url:
            meta["docx_download_url"] = download_url
            meta["docx_available"] = True
        return {
            "message_id": msg.message_id,
            "role": msg.role,
            "content": msg.content,
            "export_id": msg.export_id,
            "metadata": meta,
            "created_at": msg.created_at,
        }

    def send_message(
        self,
        user_id: str,
        conversation_id: str,
        user_text: str,
        *,
        on_status: Callable[[str, dict[str, Any] | None], None] | None = None,
    ) -> dict[str, Any]:
        def status(stage: str, detail: dict[str, Any] | None = None) -> None:
            if on_status:
                on_status(stage, detail)

        conv = self.conversations.get(conversation_id, user_id)
        if not conv:
            raise ValueError("Conversation not found")

        ctx = self._book_context(user_id, conv.book_id)
        if not ctx:
            raise ValueError("Book not found for this conversation")

        status("received")
        self.messages.add(conversation_id, "user", user_text)

        if user_requests_word_export(user_text) and not any(
            k in user_text.lower()
            for k in ("rewrite", "study notes", "revision", "summarize", "full book")
        ):
            status("exporting_word")
            result = self._handle_word_only_request(user_id, conversation_id, ctx)
            self.conversations.touch(conversation_id)
            status("done")
            return result

        status("parsing_intent")
        intent = self.parser.parse_intent(user_text)
        if not isinstance(intent, IntentResult):
            raise ValueError("Could not parse intent")

        if is_rewrite := intent.task_type in ("rewrite_book", "summarize_book", "study_notes", "revision_notes"):
            status("rewriting_book", {"task_type": intent.task_type})
            engine_result = self._run_rewrite(ctx, intent)
        else:
            status("answering_question")
            engine_result = self._run_qa(ctx, intent)

        content = engine_result.get("content") or ""
        needs_docx, reason = resolve_export_mode(intent, answer=content, user_text=user_text)

        export_id = None
        download_url = None
        docx_path = engine_result.get("docx_path")

        if needs_docx:
            status("preparing_word", {"reason": reason})
            if docx_path and os.path.exists(docx_path):
                file_name = os.path.basename(docx_path)
                record = self.exports.save(user_id, docx_path, file_name)
                export_id = record.export_id
            else:
                export_id, docx_path = self._export_answer_docx(user_id, content, ctx["title"])
            download_url = f"/api/exports/{export_id}"

        display_content = content
        if needs_docx and reason in ("qa_length", "user_request"):
            display_content = (
                f"{content}\n\n---\n\n"
                f"Your answer is long, so a Word file has been prepared.\n"
                f"Download: {download_url}"
            )
        elif needs_docx and reason == "rewrite":
            display_content = (
                f"Full book rewrite complete.\n\n"
                f"Download Word file: {download_url}\n\n"
                f"Preview (first 2000 chars):\n\n{content[:2000]}"
                f"{'...' if len(content) > 2000 else ''}"
            )

        meta = {
            "task_type": intent.task_type,
            "export_reason": reason,
            "docx_available": bool(export_id),
            "docx_download_url": download_url,
        }
        assistant = self.messages.add(
            conversation_id,
            "assistant",
            display_content,
            export_id=export_id,
            metadata=meta,
        )

        title = conv.title
        if title == "New chat" and len(user_text) > 0:
            title = generate_conversation_title(user_text, ctx["title"])
        self.conversations.touch(conversation_id, title=title)

        settings = get_auth_settings()
        status("done")
        return {
            "assistant_message": self._msg_to_dict(assistant, download_url),
            "docx_available": bool(export_id),
            "docx_download_url": download_url,
            "char_limit": settings.chat_docx_char_limit,
            "is_rewrite": is_rewrite,
        }

"""Chat orchestration: intent routing, responses, Word export."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from src import config
from src.shared.paths import resolve_project_path
from src.modules.export.word_exporter import WordExporter
from src.modules.pipeline.stage_registry import (
    STAGE_15D,
    STAGE_15E,
    STAGE_15F,
    resolve_existing_artifact,
)
from src.modules.interaction.command_parser import IntentResult, effective_user_instruction
from src.modules.interaction.intent_router import IntentRouter
from src.modules.interaction.handlers.ask_handler import AskHandler
from src.modules.interaction.handlers.rewrite_handler import RewriteHandler
from src.modules.orchestration.research_agent import ResearchAgent
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
        self.parser = IntentRouter()
        self.conversations = ConversationRepository()
        self.messages = MessageRepository()
        self.user_books = UserBookRepository()
        self.exports = ExportRepository()
        self.word_exporter = WordExporter(output_folder=config.OUTPUT_FOLDER)
        # Research agent for agentic workflows (optional alternative to IntentRouter)
        self.agent = None  # Lazy-loaded when needed

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
        file_path = resolve_project_path(ub["file_path"])
        log_dir = resolve_project_path(ub.get("log_dir"))
        return {
            "book_id": book_id,
            "title": title,
            "file_path": str(file_path) if file_path else ub["file_path"],
            "log_dir": str(log_dir) if log_dir else ub.get("log_dir"),
        }

    def _export_answer_docx(self, user_id: str, content: str, title: str) -> tuple[str, str]:
        export_dir = Path(getattr(config, "EXPORTS_FOLDER", Path(config.OUTPUT_FOLDER) / "exports")) / user_id
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
            ultimate_path = resolve_existing_artifact(log_dir, STAGE_15D)
            hierarchy_path = resolve_existing_artifact(log_dir, STAGE_15F) or resolve_existing_artifact(
                log_dir, STAGE_15E
            )

        results = handler.engine.run(
            user_instruction=effective_user_instruction(intent, intent.original_user_input),
            export_to_word=True,
            pdf_path=ctx.get("file_path"),
            ultimate_sections_path=ultimate_path,
            chapter_hierarchy_path=hierarchy_path,
            lines=lines,
            intent=intent,
        )
        if "error" in results:
            return {"content": f"Rewrite failed: {results['error']}", "docx_path": None}

        content = results.get("markdown") or "Rewrite completed."
        docx_path = results.get("docx")
        return {"content": content, "docx_path": docx_path, "task": "rewrite"}

    def _run_qa(self, ctx: dict[str, Any], intent: IntentResult, conversation_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        result = AskHandler(
            self.store,
            book_id=ctx["book_id"],
            book_title=ctx["title"],
            pdf_path=ctx.get("file_path"),
            ultimate_log_dir=ctx.get("log_dir"),
            subject_hint=ctx["title"],
            conversation_history=conversation_history or []
        ).handle_intent(intent)

        if isinstance(result, dict):
            content = result.get("answer") or "I could not generate an answer."
            sources = result.get("sources", [])
            related = result.get("related", True)
            retrieval_mode = result.get("retrieval_mode")
            reasoning = result.get("reasoning")
        else:
            content = result or "I could not generate an answer."
            sources = []
            related = True
            retrieval_mode = None
            reasoning = None

        return {
            "content": content,
            "task": "qa",
            "sources": sources,
            "related": related,
            "retrieval_mode": retrieval_mode,
            "reasoning": reasoning,
        }

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

        status("planning")
        # Get full conversation history for the agent
        messages = self.messages.list_for_conversation(conversation_id)
        conversation_history = [
            {"role": msg.role, "content": msg.content} for msg in messages[-10:]
        ]
        logger.info(f"Retrieved {len(messages)} messages from conversation {conversation_id}")
        logger.info(f"Conversation history length for agent: {len(conversation_history)}")
        if conversation_history:
            logger.info(f"Last message in history: role={conversation_history[-1]['role']}, content_length={len(conversation_history[-1]['content'])}")

        # Run agentic flow with current book context
        agent = ResearchAgent(
            user_id=user_id,
            book_context=ctx,
            max_tool_calls=5,
        )

        result = agent.run(
            query=user_text,
            conversation_history=conversation_history,
            require_approval=False,
        )

        content = result.final_answer
        status("done")

        # Metadata must stay JSON-serializable: ToolResult objects never leave this layer
        assistant = self.messages.add(
            conversation_id,
            "assistant",
            content,
            metadata={
                "task_type": "agent",
                "routing_method": "agent",
                "tool_count": len(result.tool_results),
                "total_cost_seconds": result.total_cost_seconds,
            },
        )

        title = conv.title
        if title == "New chat" and len(user_text) > 0:
            title = generate_conversation_title(user_text, ctx["title"])
        self.conversations.touch(conversation_id, title=title)

        settings = get_auth_settings()
        response = {
            "assistant_message": self._msg_to_dict(assistant),
            "docx_available": False,
            "docx_download_url": None,
            "char_limit": settings.chat_docx_char_limit,
            "is_rewrite": False,
        }
        return response

    def chat_with_agent(
        self,
        conversation_id: str,
        user_text: str,
        user_id: str,
        status: Callable[[str], None] = lambda _: None,
    ) -> dict:
        """Chat using the ResearchAgent (agentic workflow).

        This is an alternative to the legacy IntentRouter-based chat.
        The agent plans tool calls and executes them dynamically.

        Args:
            conversation_id: Conversation identifier.
            user_text: User message.
            user_id: User ID.
            status: Status callback for progress updates.

        Returns:
            Response with agent execution result.
        """
        # Lazy-load agent
        if self.agent is None:
            self.agent = ResearchAgent(user_id=user_id)

        # Get conversation context
        messages = self.messages.list_by_conversation(conversation_id)
        conversation_history = [
            {"role": msg.role, "content": msg.content} for msg in messages[-10:]
        ]

        # Get book context
        conv = self.conversations.get(conversation_id)
        if not conv:
            return {"error": "Conversation not found"}

        ctx = self._book_context(user_id, conv.book_id)
        if not ctx:
            return {"error": "Book context not found"}

        # Run agent
        status("planning")
        result = self.agent.run(
            query=user_text,
            conversation_history=conversation_history,
            require_approval=False,  # Auto-approve for now
        )

        # Store assistant message
        assistant = self.messages.add(
            conversation_id,
            "assistant",
            result.final_answer,
            metadata={
                "task_type": "agent",
                "routing_method": "agent",
                "tool_count": len(result.tool_results),
                "total_cost_seconds": result.total_cost_seconds,
            },
        )

        # Update conversation title
        title = conv.title
        if title == "New chat" and len(user_text) > 0:
            title = generate_conversation_title(user_text, ctx["title"])
        self.conversations.touch(conversation_id, title=title)

        status("done")

        return {
            "assistant_message": self._msg_to_dict(assistant),
            "agent_result": {
                "success": result.success,
                "steps": len(result.steps),
                "total_cost_seconds": result.total_cost_seconds,
            },
        }


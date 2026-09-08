import logging
from pathlib import Path
from typing import Optional

from src import config
from src.modules.pipeline.stage_registry import STAGE_15D, STAGE_15E, STAGE_15F, resolve_existing_artifact
from src.modules.export.output_manager import OutputManager
from src.modules.generation.rewrite import RewriteEngine
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.interaction.command_parser import IntentResult
from src.modules.storage.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class RewriteHandler:
    """Handles rewrite / summarize intents using 15d sections + user instruction."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        book_id: str,
        book_title: str,
        pdf_path: Optional[str] = None,
        ultimate_log_dir: Optional[str] = None,
    ) -> None:
        self.engine = RewriteEngine(
            store,
            book_id=book_id,
            book_title=book_title,
            output_folder=config.OUTPUT_FOLDER,
        )
        self.output = OutputManager(config.OUTPUT_FOLDER)
        self.pdf_path = pdf_path
        self.ultimate_log_dir = ultimate_log_dir

    def handle_intent(self, intent: IntentResult) -> str | None:
        if intent.scope == "full_book":
            import os

            # Format and length are resolved from normalized_query inside rewrite_prompts —
            # do not force EXAM_ORIENTED / COMPACT_EXAM env flags here.

            print(f"\nGenerating full-book {intent.task_type}...\n")
            from src.modules.interaction.command_parser import effective_user_instruction

            instruction = effective_user_instruction(intent)
            print(f"User instruction: {instruction}\n")

            lines = None
            ultimate_path = None
            hierarchy_path = None
            if self.pdf_path:
                lines, _, _ = extract_pdf(self.pdf_path)
            if self.ultimate_log_dir:
                log_dir = Path(self.ultimate_log_dir)
                ultimate_path = resolve_existing_artifact(log_dir, STAGE_15D)
                hierarchy_path = resolve_existing_artifact(log_dir, STAGE_15F) or resolve_existing_artifact(
                    log_dir, STAGE_15E
                )

            results = self.engine.run(
                user_instruction=instruction,
                export_to_word=True,
                pdf_path=self.pdf_path,
                ultimate_sections_path=ultimate_path,
                chapter_hierarchy_path=hierarchy_path if hierarchy_path and hierarchy_path.exists() else None,
                lines=lines,
                intent=intent,
            )
            if "error" in results:
                print(f"Error: {results['error']}")
                return None
            self.output.format_for_terminal(results["markdown"], title=self.engine.book_title)
            if results.get("docx"):
                print(f"SUCCESS: Word export at {results['docx']}")
            elif results.get("markdown_path"):
                print(f"SUCCESS: Markdown at {results['markdown_path']}")
            if results.get("section_count"):
                print(f"Sections rewritten: {results['section_count']}")
            return results.get("markdown")

        if intent.scope == "selected_topics" and getattr(intent, "target_topics", None):
            print("[!] Topic-scoped rewrite is not implemented yet. Use full_book scope.")
            return None

        print("Could not determine the scope for rewriting.")
        return None

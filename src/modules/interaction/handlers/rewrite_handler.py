import logging
from pathlib import Path
from typing import Optional

from src import config
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
            print(f"\nGenerating full-book {intent.task_type}...\n")
            print(f"User instruction: {intent.normalized_query}\n")

            lines = None
            ultimate_path = None
            hierarchy_path = None
            if self.pdf_path:
                lines, _, _ = extract_pdf(self.pdf_path)
            if self.ultimate_log_dir:
                ultimate_path = Path(self.ultimate_log_dir) / "15d_ultimate_sections.json"
                hierarchy_path = Path(self.ultimate_log_dir) / "15e_chapter_hierarchy.json"

            results = self.engine.run(
                user_instruction=intent.normalized_query,
                export_to_word=(intent.format_type == "exam_oriented"),
                pdf_path=self.pdf_path,
                ultimate_sections_path=ultimate_path,
                chapter_hierarchy_path=hierarchy_path if hierarchy_path and hierarchy_path.exists() else None,
                lines=lines,
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

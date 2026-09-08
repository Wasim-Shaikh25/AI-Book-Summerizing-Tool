import logging
import os

from src import config
from src.modules.export.output_manager import OutputManager
from src.modules.generation.rewrite import RewriteEngine
from src.modules.interaction.command_parser import IntentResult
from src.modules.storage.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class ExportHandler:
    """Export persisted book notes to Word."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        book_id: str,
        book_title: str,
    ) -> None:
        self.engine = RewriteEngine(store, book_id=book_id, book_title=book_title)
        self.output = OutputManager(config.OUTPUT_FOLDER)

    def handle_intent(self, intent: IntentResult) -> None:
        if intent.scope == "full_book":
            self.handle_export_book()
        else:
            print("[!] Export supports full_book scope only in this version.")

    def handle_export_book(self, *, user_instruction: str = "") -> None:
        print("\nGenerating notes and exporting to Word...\n")
        instruction = user_instruction or os.getenv("REWRITE_USER_INSTRUCTION", "").strip()
        if not instruction:
            instruction = "Rewrite into clear structured notes."
        results = self.engine.run(user_instruction=instruction, export_to_word=True)
        if "error" in results:
            print(f"Error: {results['error']}")
            return
        self.output.format_for_terminal(results["markdown"], title=f"Export: {self.engine.book_title}")
        print(f"SUCCESS! Word file: {results.get('docx', config.OUTPUT_FOLDER)}")

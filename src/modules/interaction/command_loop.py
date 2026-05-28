import logging
import os
from typing import Any, Optional

from src import config
from src.modules.export.word_exporter import WordExporter
from src.modules.interaction.command_parser import CommandParser, IntentResult
from src.modules.interaction.handlers.export_handler import ExportHandler
from src.modules.interaction.handlers.rewrite_handler import RewriteHandler
from src.modules.pipeline import run_pipeline
from src.modules.storage.book_repository import BookRepository
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.schema import BookMetadata
from src.modules.storage.toc_repository import TocRepository

logger = logging.getLogger(__name__)


class CommandLoop:
    """Interactive CLI for ingestion, rewrite, and export."""

    def __init__(self) -> None:
        self.parser = CommandParser()
        self.store = KnowledgeStore()
        self.book_repo = BookRepository(self.store)
        self.toc_repo = TocRepository(self.store)
        self.word_exporter = WordExporter(output_folder=config.OUTPUT_FOLDER)
        self.current_file_path: Optional[str] = None
        self.current_book_id: Optional[str] = None
        self.current_book_title: Optional[str] = None
        self.last_log_dir: Optional[str] = None
        self.last_generated_response: Optional[str] = None
        self.running = True

    def start(self) -> None:
        print("\n" + "=" * 50)
        print("AI KNOWLEDGE ENGINE - INTERACTIVE CHAT")
        print("Provide a PDF path to ingest, then ask for rewrite/export.")
        print("Type 'help' or 'exit'.")
        print("=" * 50 + "\n")

        while self.running:
            try:
                user_input = input("You> ").strip()
                if not user_input:
                    continue

                clean_input = user_input.strip().strip('"').strip("'").replace("\n", "").replace("\r", "")

                if clean_input.lower().endswith(".pdf") and os.path.exists(clean_input):
                    self._handle_ingestion(clean_input)
                    continue
                if clean_input.lower().endswith(".pdf"):
                    print(f"[!] File not found: {clean_input}")
                    continue

                result = self.parser.parse_intent(user_input)
                if result == "exit":
                    self.running = False
                    print("Goodbye!")
                elif result == "help":
                    self._show_help()
                elif result == "export":
                    self._handle_export_last()
                elif isinstance(result, IntentResult):
                    self._process_intent_pipeline(result)
                else:
                    print("I didn't understand that. Type 'help' for usage.")
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit.")
            except Exception as e:
                logger.error("Error in command loop: %s", e, exc_info=True)
                print(f"An error occurred: {e}")

    def _require_book(self) -> bool:
        if not self.current_book_id:
            print("[!] Ingest a PDF first (paste full path).")
            return False
        return True

    def _process_intent_pipeline(self, intent: IntentResult) -> None:
        if not self._require_book():
            return

        print(f"[*] Processing {intent.task_type}...")
        book_id = self.current_book_id or ""
        title = self.current_book_title or "Book"

        if intent.task_type in ("rewrite_book", "summarize_book", "study_notes", "revision_notes"):
            md = RewriteHandler(
                self.store,
                book_id=book_id,
                book_title=title,
                pdf_path=self.current_file_path,
                ultimate_log_dir=self.last_log_dir,
            ).handle_intent(intent)
            if md:
                self.last_generated_response = md
            return

        if intent.scope == "full_book" and intent.format_type == "exam_oriented":
            ExportHandler(self.store, book_id=book_id, book_title=title).handle_intent(intent)
            return

        print(
            "[!] Q&A for single questions is not wired yet. "
            "Try: 'rewrite the book in simple English' after ingestion."
        )

    def _handle_export_last(self) -> None:
        if self.last_generated_response:
            print("[*] Exporting last generated answer to Word...")
            try:
                book_data = self.word_exporter.assemble_full_book_structured_text(
                    [self.last_generated_response], "Exported_Notes"
                )
                file_path = self.word_exporter.structured_text_to_word(
                    book_data, "Exported_Notes.docx", include_toc=False
                )
                print(f"[+] Successfully exported to: {file_path}")
            except Exception as e:
                logger.error("Export failed: %s", e)
                print(f"[!] Export failed: {e}")
            return

        if self._require_book():
            ExportHandler(
                self.store,
                book_id=self.current_book_id or "",
                book_title=self.current_book_title or "Book",
            ).handle_export_book()

    def _handle_ingestion(self, file_path: str) -> None:
        print(f"[*] Ingesting file: {file_path}")
        try:
            from src.modules.ingestion.pdf_extractor import extract_pdf

            lines, book_title, _visual = extract_pdf(file_path)
            pages = {ln.page_number for ln in lines if getattr(ln, "page_number", None) is not None}
            total_pages = max(pages) if pages else 0
            title = book_title or os.path.splitext(os.path.basename(file_path))[0]

            book = BookMetadata(
                title=title,
                source_file_name=os.path.basename(file_path),
                total_pages=total_pages,
            )
            self.book_repo.save_book(book)

            result, logger = run_pipeline(file_path, enable_logs=True, persist_to_db=False)
            self.last_log_dir = str(logger.run_dir) if logger else None
            self.toc_repo.save_full_toc(
                book_id=book.book_id,
                final_headings=result.final_headings,
                fragments=result.fragments,
                heading_to_fragment_id=result.heading_to_fragment_id,
                clear_existing=True,
            )

            self.current_file_path = file_path
            self.current_book_id = book.book_id
            self.current_book_title = title
            self.last_generated_response = None

            print("[+] Ingestion complete.")
            print(f"    book_id: {book.book_id}")
            print(f"    final_headings: {len(result.final_headings)}")
            print(f"    fragments: {len(result.fragments)}")
            if self.last_log_dir:
                print(f"    logs: {self.last_log_dir}")
        except Exception as e:
            logger.error("Ingestion failed: %s", e, exc_info=True)
            print(f"[!] Ingestion failed: {e}")

    def _show_help(self) -> None:
        print("\nAVAILABLE COMMANDS:")
        print("  exit          - Quit")
        print("  help          - This message")
        print("  export        - Export last answer or full book to Word")
        print("  [PDF path]    - Ingest a book")
        print("\nEXAMPLES (after ingestion):")
        print("  rewrite the book in short simple English, no extra details")
        print("  create exam oriented study notes")
        print("  export book")
        print()

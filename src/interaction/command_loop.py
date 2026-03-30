import logging
import os
from typing import Any, Optional

from src.core.pipeline import run_pipeline

from src.config import OUTPUT_FOLDER
from src.generation.content_generation import ContentGenerationEngine
from src.export.word_exporter import WordExporter
from src.interaction.command_parser import CommandParser, IntentResult
from src.storage.book_repository import BookRepository
from src.storage.knowledge_store import KnowledgeStore
from src.storage.schema import BookMetadata
from src.storage.toc_repository import TocRepository
from src.storage.topic_repository import TopicRepository

logger = logging.getLogger(__name__)

class CommandLoop:
    """
    The main terminal-based command loop for the Knowledge Engine.
    Implements the Intent Processing Pipeline.
    """
    def __init__(self):
        self.parser = CommandParser()
        self.store = KnowledgeStore()

        self.book_repo = BookRepository(self.store)
        self.topic_repo = TopicRepository(self.store)
        self.toc_repo = TocRepository(self.store)

        self.retrieval_engine = None
        self.gen_engine = ContentGenerationEngine()
        self.word_exporter = WordExporter(output_folder=OUTPUT_FOLDER)
        self.rewriter: Optional[Any] = None
        self.current_file_path: Optional[str] = None

        self.last_generated_response: Optional[str] = None
        self.running = True

    def start(self):
        print("\n" + "="*50)
        print("AI KNOWLEDGE ENGINE - INTERACTIVE CHAT")
        print("Please provide a full PDF file path to begin, or type 'exit' to quit.")
        print("="*50 + "\n")

        while self.running:
            try:
                user_input = input("You> ").strip()
                if not user_input:
                    continue
                
                # Clean input (strip quotes and newlines which often come from terminal wrapping)
                clean_input = user_input.strip().strip('"').strip("'").replace('\n', '').replace('\r', '')
                
                # Check if input is a file path
                if clean_input.lower().endswith(".pdf") and (os.path.exists(clean_input) or (":" in clean_input and "\\" in clean_input)):
                    if os.path.exists(clean_input):
                        self._handle_ingestion(clean_input)
                    else:
                        print(f"[!] File not found: {clean_input}")
                    continue

                # STEP 1: Intent Understanding (Fixed commands or Gemini analysis)
                result = self.parser.parse_intent(user_input)
                
                if result == "exit":
                    self.running = False
                    print("Goodbye!")
                    continue
                elif result == "help":
                    self._show_help()
                    continue
                elif result == "export":
                    self._handle_export()
                    continue
                
                if isinstance(result, IntentResult):
                    self._process_intent_pipeline(result)
                else:
                    print("I didn't understand that. Type 'help' for usage.")
            
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit.")
            except Exception as e:
                logger.error(f"Error in command loop: {e}")
                print(f"An error occurred: {e}")

    def _process_intent_pipeline(self, intent: IntentResult):
        """
        Executes the 4-step Intent Processing Pipeline.
        """
        if not self.rewriter and intent.scope == "full_book":
            print("[!] Please ingest a book first by providing its file path.")
            return

        print(f"[*] Processing {intent.task_type}...")

        if intent.scope == "full_book" and self.rewriter:
            # Use the specialized pipeline for full book operations
            results = self.rewriter.run(intent=intent, export_to_word=True, specific_file=self.current_file_path)
            if "error" in results:
                print(f"[!] Error: {results['error']}")
                return
            response = results['markdown']
        else:
            # NOTE: RetrievalEngine was removed in the current architecture.
            # This interactive Q&A path needs a new retrieval implementation.
            raise NotImplementedError(
                "Interactive Q&A retrieval is not wired in this version. "
                "Ingest a book and use full_book intents, or implement a retrieval adapter."
            )
        
        if response:
            print("\n" + "-"*30)
            print(response)
            print("-"*30 + "\n")
            self.last_generated_response = response
        else:
            print("[!] Failed to generate content.")

    def _handle_export(self):
        if not self.last_generated_response:
            print("[!] Warning: No answer exists yet to export. Please ask a question or request notes first.")
            return
        
        print("[*] Exporting last generated answer to Word...")
        try:
            # Using existing document formatting rules via WordExporter
            # We'll use a generic title for individual exports
            book_data = self.word_exporter.assemble_full_book_structured_text(
                [self.last_generated_response], 
                "Exported_Notes"
            )
            # Disable TOC for single answer exports to keep it direct
            file_path = self.word_exporter.structured_text_to_word(
                book_data, 
                "Exported_Notes.docx",
                include_toc=False
            )
            print(f"[+] Successfully exported to: {file_path}")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            print(f"[!] Export failed: {e}")

    def _handle_ingestion(self, file_path: str):
        """
        Handles the ingestion of a new PDF file.

        Production behavior:
        - Run the clean deterministic core pipeline
        - Persist final headings + fragments (+ relationship) to DB
        - Stage JSON traces remain optional and are not generated unless enabled elsewhere
        """
        import os

        print(f"[*] Ingesting file: {file_path}")

        try:
            from src.ingestion.pdf_extractor import extract_pdf

            # Extract lightweight PDF metadata for the books table
            pdf_doc = extract_pdf(file_path)
            total_pages = int(getattr(pdf_doc, "page_count", 0) or 0)
            title = os.path.splitext(os.path.basename(file_path))[0]

            book = BookMetadata(
                title=title,
                source_file_name=os.path.basename(file_path),
                total_pages=total_pages,
            )
            self.book_repo.save_book(book)

            # Run pipeline (no stage logs in production ingestion)
            result, _logger = run_pipeline(file_path, enable_logs=False)

            # Optional cleanup: we only keep book metadata + finalized TOC structure in DB.
            # Topics are legacy/derived and are not used once the final TOC snapshot exists.
            conn = self.store.get_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM topics WHERE book_id = ?", (book.book_id,))
                conn.commit()
            finally:
                conn.close()

            # Persist finalized TOC snapshot (DB is the source of truth)
            self.toc_repo.save_full_toc(
                book_id=book.book_id,
                final_headings=result.final_headings,
                fragments=result.fragments,
                heading_to_fragment_id=result.heading_to_fragment_id,
                clear_existing=True,
            )

            self.rewriter = None
            self.current_file_path = file_path

            print("[+] Ingestion complete.")
            print(f"    book_id: {book.book_id}")
            print(f"    final_headings: {len(result.final_headings)}")
            print(f"    fragments: {len(result.fragments)}")
        except Exception as e:
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            print(f"[!] Ingestion failed: {e}")

    def _show_help(self):
        print("\nAVAILABLE COMMANDS:")
        print("  exit                       - Immediately stops the system safely.")
        print("  help                       - Displays this usage instructions.")
        print("  export                     - Exports the LAST GENERATED ANSWER into a Word (.docx) file.")
        print("  [File Path]                - Provide a full .pdf path to ingest a new book.")
        print("\nDYNAMIC USER INTENT EXAMPLES:")
        print("  - 'rewrite the book in simple English'")
        print("  - 'give me full book summary'")
        print("  - 'create short study notes'")
        print("  - 'create revision notes'")
        print("  - 'answer this question: what is photosynthesis?'")
        print("\nNote: Formatting is system-controlled to ensure academic quality.\n")

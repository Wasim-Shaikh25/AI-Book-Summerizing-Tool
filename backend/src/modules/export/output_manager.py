import logging
from typing import Any, Dict, Optional

from src.modules.export.document_formatter import BookCoverMeta
from src.modules.export.word_exporter import WordExporter

logger = logging.getLogger(__name__)

class OutputManager:
    """
    Manages fixed formatting for terminal and Word document outputs.
    Ensures consistency across all modes and prevents user overrides.
    """
    def __init__(self, output_folder: str):
        self.output_folder = output_folder
        self.word_exporter = WordExporter(output_folder)

    def format_for_terminal(self, content: str, title: str = "AI KNOWLEDGE ENGINE"):
        """
        Prints clean, structured output to the terminal.
        """
        print("\n" + "="*60)
        print(f" {title.upper()} ")
        print("="*60 + "\n")
        
        # Ensure clear separation of sections
        formatted_content = content.replace("### ", "\n--- ").replace("## ", "\n\n## ")
        print(formatted_content)
        print("\n" + "="*60 + "\n")

    def export_to_word(
        self,
        content: str,
        filename: str,
        title: str,
        toc_depth: int = 3,
        include_toc: bool = False,
        *,
        cover: Optional[BookCoverMeta] = None,
        hierarchy: Optional[Dict[str, Any]] = None,
        rewritten: Optional[Dict[str, str]] = None,
        bundle_size: int = 1,
        bundle_export: bool = False,
        compact_toc: bool = False,
        chapter_page_breaks: Optional[bool] = None,
    ) -> str:
        """
        Exports content to Word. Prefer structured export (cover, TOC, page breaks)
        when hierarchy + rewritten map are supplied; otherwise Pandoc markdown.
        """
        logger.info(f"Exporting to Word: {filename}")

        if cover is not None and hierarchy is not None and rewritten is not None:
            try:
                return self.word_exporter.structured_notes_to_word(
                    output_filename=filename,
                    cover=cover,
                    hierarchy=hierarchy,
                    rewritten=rewritten,
                    bundle_size=bundle_size,
                    bundle_export=bundle_export,
                    compact_toc=compact_toc,
                    chapter_page_breaks=chapter_page_breaks,
                )
            except Exception as e:
                logger.error(f"Structured Word export failed, falling back to Pandoc: {e}")

        book_data = {"title": title, "content": content}
        try:
            path = self.word_exporter.structured_text_to_word(
                book_data,
                filename,
                toc_depth=toc_depth,
                include_toc=include_toc,
            )
            return path
        except Exception as e:
            logger.error(f"Word export failed: {e}")
            return ""

    def handle_output(self, content: str, intent: Any, title: str = "Generated Content"):
        """
        Routes content to the appropriate output format based on intent.
        """
        # 1. Always show in terminal for immediate feedback
        self.format_for_terminal(content, title)
        
        # Export to Word when exam-oriented format requested
        if getattr(intent, "format_type", "") == "exam_oriented":
            filename = f"{title.replace(' ', '_')}.docx"
            path = self.export_to_word(content, filename, title)
            if path:
                print(f"SUCCESS: Document exported to {path}")
            else:
                print("ERROR: Failed to export Word document.")

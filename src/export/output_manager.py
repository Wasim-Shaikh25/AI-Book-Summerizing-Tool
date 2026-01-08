import logging
import os
from typing import List, Dict, Any
from src.export.word_exporter import WordExporter

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

    def export_to_word(self, content: str, filename: str, title: str, toc_depth: int = 3) -> str:
        """
        Exports content to a Word document with fixed styles.
        """
        logger.info(f"Exporting to Word: {filename}")
        
        book_data = {
            "title": title,
            "content": content
        }
        
        # The WordExporter uses Pandoc with a reference docx for fixed styles
        try:
            path = self.word_exporter.structured_text_to_word(
                book_data, 
                filename, 
                toc_depth=toc_depth
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
        
        # 2. Export to Word only if explicitly requested in intent
        if intent.output_format == "word_document":
            filename = f"{title.replace(' ', '_')}.docx"
            path = self.export_to_word(content, filename, title)
            if path:
                print(f"SUCCESS: Document exported to {path}")
            else:
                print("ERROR: Failed to export Word document.")

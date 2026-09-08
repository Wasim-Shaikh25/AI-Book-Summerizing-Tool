import logging
import os
import subprocess  # Import subprocess for running Pandoc
import tempfile  # Import tempfile for creating temporary files
from typing import Optional

from docx import Document

from src.config import REFERENCE_DOCX_PATH  # Import the reference docx path
from src.modules.export.docx_notes_exporter import DocxNotesExporter
from src.modules.export.document_formatter import BookCoverMeta

logger = logging.getLogger(__name__)

class WordExporter:
    """
    Handles the export of structured text content into a Word (.docx) document.
    """
    def __init__(self, output_folder: str):
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)

    def assemble_full_book_structured_text(self, structured_notes_list: list[str], book_title: str) -> dict:
        """
        Assembles the structured notes into a dictionary format suitable for Word export.
        This is a placeholder and can be expanded for more complex structures.
        """
        full_content = "\n\n".join(structured_notes_list)
        return {"title": book_title, "content": full_content}

    def _save_text_file(self, content: str, filename: str) -> str:
        """Saves raw text content to a file in the output folder."""
        filepath = os.path.join(self.output_folder, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def export_markdown_to_word(
        self,
        md_text: str,
        output_filename: str,
        *,
        reference_docx: Optional[str] = None,
    ) -> str:
        """Convert notes markdown to DOCX preserving MD structure (headings, lists, page breaks)."""
        from src.modules.export.markdown_docx_renderer import export_markdown_file_to_docx

        output_path = os.path.join(self.output_folder, output_filename)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                logger.error("Error removing existing output file %s: %s", output_path, e)
                raise
        ref = reference_docx or (REFERENCE_DOCX_PATH if os.path.exists(REFERENCE_DOCX_PATH) else None)
        return export_markdown_file_to_docx(md_text, output_path, reference_docx=ref)

    def structured_notes_to_word(
        self,
        *,
        output_filename: str,
        cover: BookCoverMeta,
        hierarchy: dict,
        rewritten: dict[str, str],
        bundle_size: int = 1,
        bundle_export: bool = False,
        compact_toc: bool = False,
        chapter_page_breaks: Optional[bool] = None,
    ) -> str:
        """Export notes with cover, hierarchical TOC, and chapter page breaks (python-docx)."""
        output_path = os.path.join(self.output_folder, output_filename)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                logger.error("Error removing existing output file %s: %s", output_path, e)
                raise
        return DocxNotesExporter().export(
            output_path,
            cover=cover,
            hierarchy=hierarchy,
            rewritten=rewritten,
            reference_docx=REFERENCE_DOCX_PATH if os.path.exists(REFERENCE_DOCX_PATH) else None,
            bundle_size=bundle_size,
            bundle_export=bundle_export,
            compact_toc=compact_toc,
            chapter_page_breaks=chapter_page_breaks,
        )

    def structured_text_to_word(self, book_data: dict, output_filename: str, toc_depth: int = 3, include_toc: bool = True) -> str:
        """
        Converts structured text data into a Word document using Pandoc
        and a reference DOCX for styling.
        """
        output_path = os.path.join(self.output_folder, output_filename)
        
        # Ensure the output file does not exist to prevent permission errors
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Removed existing output file: {output_path}")
            except OSError as e:
                logger.error(f"Error removing existing output file {output_path}: {e}")
                raise

        # Create a temporary markdown file. The overall book title will not be added.
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md', encoding='utf-8') as temp_md_file:
            temp_md_file.write(book_data.get("content", ""))
            temp_md_path = temp_md_file.name

        try:
            # Construct the Pandoc command to convert markdown to docx
            pandoc_command = [
                "pandoc",
                temp_md_path,
                "-o", output_path,
                "--from", "markdown",
                "--reference-doc", REFERENCE_DOCX_PATH,
            ]
            
            if include_toc:
                pandoc_command.extend([
                    "--toc",
                    f"--toc-depth={toc_depth}"
                ])

            logger.info(f"Running Pandoc command: {' '.join(pandoc_command)}")
            
            # Execute Pandoc
            result = subprocess.run(pandoc_command, capture_output=True, text=True, check=True)
            logger.info(f"Pandoc stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"Pandoc stderr: {result.stderr}")

            logger.info(f"Word document saved to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            logger.error(f"Pandoc conversion failed: {e}")
            logger.error(f"Pandoc stdout: {e.stdout}")
            logger.error(f"Pandoc stderr: {e.stderr}")
            raise
        except FileNotFoundError:
            logger.error("Pandoc not found. Please ensure Pandoc is installed and in your PATH.")
            raise
        finally:
            # Clean up the temporary markdown file
            if os.path.exists(temp_md_path):
                os.remove(temp_md_path)

if __name__ == "__main__":
    # Example usage
    output_folder_example = "output_test"
    os.makedirs(output_folder_example, exist_ok=True)

    exporter = WordExporter(output_folder=output_folder_example)

    sample_notes = [
        "# Main Title Example",
        "## Chapter 1: Introduction to Contracts",
        "This is an introductory paragraph about contracts. It should be justified.",
        "- Definition of a contract",
        "* Essential elements: Offer, Acceptance, Consideration",
        "1. First point of a numbered list",
        "2. Second point of a numbered list",
        "### Section: Key Principles",
        "This section discusses **key principles** like *Freedom of Contract* and Sanctity of Contract. It should also be justified.",
        "## Chapter 2: Advanced Topics",
        "Another paragraph here, also justified."
    ]
    sample_title = "Sample Book Notes"

    book_data_example = exporter.assemble_full_book_structured_text(sample_notes, sample_title)
    
    # Ensure a dummy reference.docx exists for the example to run
    dummy_reference_path = os.path.join("reference_files", "reference.docx")
    if not os.path.exists(dummy_reference_path):
        os.makedirs(os.path.dirname(dummy_reference_path), exist_ok=True)
        Document().save(dummy_reference_path)
        print(f"Created dummy reference.docx at {dummy_reference_path} for example.")

    try:
        word_file_path = exporter.structured_text_to_word(book_data_example, "Sample_Notes_Formatted_Pandoc.docx")
        print(f"Generated sample Word document: {word_file_path}")
    except Exception as e:
        print(f"Error during example Pandoc conversion: {e}")

    raw_text_file_path = exporter._save_text_file("\n\n".join(sample_notes), "sample_notes_raw.txt")
    print(f"Generated sample raw text file: {raw_text_file_path}")

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os
import logging
import re
import subprocess # Import subprocess for running Pandoc
import tempfile # Import tempfile for creating temporary files

from src.config import REFERENCE_DOCX_PATH # Import the reference docx path

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

    def structured_text_to_word(self, book_data: dict, output_filename: str) -> str:
        """
        Converts structured text data into a Word document using Pandoc
        and a reference DOCX for styling.
        """
        output_path = os.path.join(self.output_folder, output_filename)
        
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
                "--reference-doc", REFERENCE_DOCX_PATH,
                "--toc", # Add table of contents
                "--toc-depth=3" # Up to heading level 3 in TOC
            ]

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
    sample_title = "Sample Contract Law Notes"

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

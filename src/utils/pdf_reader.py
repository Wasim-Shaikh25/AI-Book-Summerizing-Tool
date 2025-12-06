import os
import re
import logging
from typing import List, Tuple

from pypdf import PdfReader

logger = logging.getLogger(__name__)

class PDFReader:
    def __init__(self, pdf_folder: str):
        self.pdf_folder = pdf_folder

    def _extract_book_title_from_filenames(self, filenames: List[str]) -> str:
        """
        Extracts a clean book title from a list of PDF filenames.
        Tries to find common patterns and remove noise.
        """
        if not filenames:
            return "Rewritten Book Notes"

        # Take the first filename as a base
        base_name = os.path.splitext(filenames[0])[0]

        # Remove common suffixes/patterns
        base_name = re.sub(r'\[\d+-\d+\]', '', base_name) # e.g., [1-5]
        base_name = re.sub(r'Notes\s*(MU)?\s*(New\s*syllabus)?\s*\d{4}\s*\d{2}\s*\d{2}', '', base_name, flags=re.IGNORECASE) # e.g., Notes MU New syllabus 2022 23
        base_name = re.sub(r'Notes\s*(\d{4}\s*\d{2}\s*\d{2})?', '', base_name, flags=re.IGNORECASE) # e.g., Notes 2022 23
        base_name = re.sub(r'Notes', '', base_name, flags=re.IGNORECASE) # generic "Notes"
        base_name = re.sub(r'PDF', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'final', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'summary', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'chapter\s*\d+', '', base_name, flags=re.IGNORECASE)

        # Clean up extra spaces and trim
        title = re.sub(r'\s+', ' ', base_name).strip()

        if not title:
            return "Rewritten Book Notes"
        return title

    def read_all_pdfs(self) -> Tuple[str, str]:
        """
        Reads all PDF files from the specified folder, concatenates their text,
        and extracts a dynamic book title.
        Returns a tuple of (full_text, book_title).
        """
        text_parts: List[str] = []
        pdf_filenames: List[str] = []
        files = [f for f in os.listdir(self.pdf_folder) if f.lower().endswith(".pdf")]
        if not files:
            raise FileNotFoundError(f"No PDFs found in '{self.pdf_folder}'. Please place PDF files there.")
        
        for file in files:
            logger.info(f"Reading {file} ...")
            pdf_filenames.append(file)
            try:
                reader = PdfReader(os.path.join(self.pdf_folder, file))
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        text_parts.append(txt)
            except Exception as e:
                logger.error(f"Error reading PDF {file}: {e}")
                continue # Continue to next PDF if one fails
        
        full_text = "\n\n".join(text_parts)
        if not full_text:
            raise ValueError("No text could be extracted from the provided PDFs.")
        
        book_title = self._extract_book_title_from_filenames(pdf_filenames)
        return full_text, book_title

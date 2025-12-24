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

    def extract_headings_from_text(self, text: str) -> List[Tuple[str, int]]:
        """
        Extracts potential headings and their hierarchical levels from the raw PDF text.
        This function infers structure based on common heading patterns.
        Returns a list of (heading_text, level) tuples.
        """
        headings: List[Tuple[str, int]] = []
        lines = text.split('\n')

        # Regex patterns for different heading levels
        # Level 1: Lines starting with "MODULE X:", "CHAPTER X:", or "X.Y " (e.g., "1.1 ")
        # Level 2: Lines starting with "A. ", "B. ", "I. ", "II. "
        # Level 3: Lines starting with "1. ", "2. ", "a. ", "b. "
        # Also consider all-caps lines as potential headings

        # Pattern for main sections (e.g., "MODULE 1:", "1.1 Tort: Definition...")
        # This is a bit tricky as "1.1" can be a top-level or sub-level depending on context.
        # For now, let's prioritize explicit markers.
        re_h1 = re.compile(r'^(?:MODULE\s+\d+:|CHAPTER\s+\d+:|\d+\.\d+\s+)(.*)', re.IGNORECASE)
        re_h2 = re.compile(r'^(?:[A-Z]\.\s+)(.*)') # e.g., "A. INTRODUCTION:"
        re_h3 = re.compile(r'^(?:\d+\.\s+)(.*)') # e.g., "1. Definition of Tort"
        re_h4 = re.compile(r'^(?:[a-z]\.\s+)(.*)') # e.g., "a. Distinction between..."

        # Keep track of the last identified level to infer hierarchy
        last_level = 0

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

            # Try to match H1
            match_h1 = re_h1.match(stripped_line)
            if match_h1:
                headings.append((match_h1.group(0).strip(), 1))
                last_level = 1
                continue

            # Try to match H2
            match_h2 = re_h2.match(stripped_line)
            if match_h2:
                headings.append((match_h2.group(0).strip(), 2))
                last_level = 2
                continue

            # Try to match H3
            match_h3 = re_h3.match(stripped_line)
            if match_h3:
                headings.append((match_h3.group(0).strip(), 3))
                last_level = 3
                continue
            
            # Try to match H4
            match_h4 = re_h4.match(stripped_line)
            if match_h4:
                headings.append((match_h4.group(0).strip(), 4))
                last_level = 4
                continue

            # Fallback for all-caps lines that might be headings but don't fit other patterns
            if stripped_line.isupper() and len(stripped_line.split()) <= 10 and len(stripped_line) > 5:
                # Assign a level based on the last known level, or default to 2
                inferred_level = min(last_level + 1, 3) if last_level > 0 else 2
                headings.append((stripped_line, inferred_level))
                last_level = inferred_level
                continue

        logger.info(f"Extracted {len(headings)} potential headings from PDF text.")
        return headings

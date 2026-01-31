import os
import re
import logging
import fitz  # PyMuPDF
from typing import List, Tuple, Dict, Any
from src.utils.ocr_reader import OCRReader

logger = logging.getLogger(__name__)

class PDFReader:
    """
    Reads PDF files, extracts text, and routes image-only pages to OCR.
    """
    def __init__(self, pdf_folder: str):
        self.pdf_folder = pdf_folder
        self.ocr_reader = OCRReader()

    def _extract_book_title_from_filenames(self, filenames: List[str]) -> str:
        if not filenames:
            return "Rewritten Book Notes"
        base_name = os.path.splitext(filenames[0])[0]
        base_name = re.sub(r'\[\d+-\d+\]', '', base_name)
        base_name = re.sub(r'Notes\s*(MU)?\s*(New\s*syllabus)?\s*\d{4}\s*\d{2}\s*\d{2}', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'Notes\s*(\d{4}\s*\d{2}\s*\d{2})?', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'Notes', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'PDF', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'final', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'summary', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'chapter\s*\d+', '', base_name, flags=re.IGNORECASE)
        title = re.sub(r'\s+', ' ', base_name).strip()
        return title if title else "Rewritten Book Notes"

    def read_all_pdfs(self, specific_file: str = None) -> Tuple[List[Dict[str, Any]], str]:
        """
        Reads PDFs, detects image-only pages, and returns a list of page data.
        If specific_file is provided, only that file is read.
        Returns: (List of {"text": str, "page_number": int}, book_title)
        """
        pages_data: List[Dict[str, Any]] = []
        pdf_filenames: List[str] = []
        
        if specific_file:
            if os.path.isabs(specific_file):
                files = [specific_file]
            else:
                files = [os.path.join(self.pdf_folder, specific_file)]
        else:
            if not os.path.exists(self.pdf_folder):
                raise FileNotFoundError(f"PDF folder '{self.pdf_folder}' does not exist.")
            files = [os.path.join(self.pdf_folder, f) for f in os.listdir(self.pdf_folder) if f.lower().endswith(".pdf")]
        
        if not files:
            raise FileNotFoundError(f"No PDFs found.")
        
        total_page_counter = 1
        for pdf_path in files:
            file_name = os.path.basename(pdf_path)
            logger.info(f"Processing {file_name} ...")
            pdf_filenames.append(file_name)
            
            try:
                doc = fitz.open(pdf_path)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    text = page.get_text().strip()
                    
                    if not text:
                        # Image-only page detected
                        logger.info(f"Image-only page detected: Page {page_num + 1}. Routing to OCR...")
                        ocr_results = self.ocr_reader.extract_text_from_page_images(doc, page_num)
                        # The OCRReader now returns results only for the specific page, so no filtering needed.
                        page_ocr_text = "\n".join([res["text"] for res in ocr_results])
                        if page_ocr_text:
                            pages_data.append({"text": f"[SOURCE: IMAGE] {page_ocr_text}", "page_number": total_page_counter})
                    else:
                        pages_data.append({"text": text, "page_number": total_page_counter})
                    total_page_counter += 1
                doc.close()
            except Exception as e:
                logger.error(f"Error processing PDF {file_name}: {e}")
                continue
        
        if not pages_data:
            raise ValueError("No text could be extracted from the provided PDFs.")
        
        book_title = self._extract_book_title_from_filenames(pdf_filenames)
        return pages_data, book_title

import logging
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class OCRReader:
    """
    Extracts images from PDF pages and performs OCR using Tesseract.
    """
    def __init__(self, tesseract_cmd: str = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def extract_text_from_page(self, doc: fitz.Document, page_num: int) -> str:
        """
        Extracts images from a specific page and performs OCR.
        """
        page_text_parts = []
        try:
            page = doc.load_page(page_num)
            image_list = page.get_images(full=True)
            
            if not image_list:
                return ""
            
            logger.info(f"Found {len(image_list)} images on page {page_num + 1}")
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                try:
                    image = Image.open(io.BytesIO(image_bytes))
                    text = pytesseract.image_to_string(image).strip()
                    if text:
                        page_text_parts.append(text)
                except Exception as e:
                    logger.error(f"OCR failed for image {img_index} on page {page_num + 1}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1} for OCR: {e}")
            
        return "\n".join(page_text_parts)

    def extract_text_from_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Iterates through PDF pages, extracts images, and performs OCR.
        """
        results = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page_text = self.extract_text_from_page(doc, page_num)
                if page_text:
                    results.append({
                        "text": page_text,
                        "page_number": page_num + 1,
                        "source_type": "image"
                    })
            doc.close()
        except Exception as e:
            logger.error(f"Failed to process PDF for OCR: {e}")
            
        return results

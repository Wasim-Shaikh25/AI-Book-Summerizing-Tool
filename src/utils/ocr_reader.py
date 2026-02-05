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

    def extract_text_from_page_images(self, doc: fitz.Document, page_num: int) -> List[Dict[str, Any]]:
        """
        Extracts images from a specific PDF page and performs OCR using Tesseract.
        """
        results = []
        try:
            page = doc.load_page(page_num)
            image_list = page.get_images(full=True)
            
            if not image_list:
                return results
            
            logger.info(f"Found {len(image_list)} images on page {page_num + 1}")
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                try:
                    image = Image.open(io.BytesIO(image_bytes))
                    text = pytesseract.image_to_string(image).strip()
                    
                    if text:
                        results.append({
                            "text": text,
                            "page_number": page_num + 1,
                            "source_type": "image"
                        })
                except Exception as e:
                    logger.error(f"OCR failed for image {img_index} on page {page_num + 1}: {e}")
                    # Graceful fallback: continue to next image
                    continue
        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1} for OCR: {e}")
            
        return results

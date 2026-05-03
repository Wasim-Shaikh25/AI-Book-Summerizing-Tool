import io
import logging
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

class OCRReader:
    """
    Extracts images from PDF pages and performs OCR using Tesseract.
    """
    def __init__(self, tesseract_cmd: str = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def extract_text_from_region(self, pdf_path: str, page_num: int, bbox: List[float]) -> str:
        """
        OCR a specific bounding-box region on one page (1-based page_num).

        Renders only the clipped region at 2x zoom for quality, then runs
        pytesseract.  Never scans the entire PDF — fixes the whole-document hang.
        """
        try:
            doc = fitz.open(pdf_path)
            try:
                page = doc.load_page(page_num - 1)
                clip = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat, clip=clip)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text = pytesseract.image_to_string(img).strip()
                return text
            finally:
                doc.close()
        except Exception as e:
            logger.error(f"OCR region failed page={page_num} bbox={bbox}: {e}")
            return ""

    def extract_text_from_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Iterates through PDF pages, extracts images, and performs OCR.
        """
        results = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                image_list = page.get_images(full=True)
                
                if not image_list:
                    continue
                
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
            doc.close()
        except Exception as e:
            logger.error(f"Failed to process PDF for OCR: {e}")
            
        return results

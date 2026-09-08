import io
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

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

    def _render_region(self, pdf_path: str, page_num: int, bbox: List[float], zoom: float = 2.0) -> Image.Image:
        doc = fitz.open(pdf_path)
        try:
            page = doc.load_page(page_num - 1)
            clip = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            mat = fitz.Matrix(float(zoom), float(zoom))
            pix = page.get_pixmap(matrix=mat, clip=clip)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        finally:
            doc.close()

    def extract_text_from_region(self, pdf_path: str, page_num: int, bbox: List[float]) -> str:
        """
        OCR a specific bounding-box region on one page (1-based page_num).

        Renders only the clipped region at 2x zoom for quality, then runs
        pytesseract.  Never scans the entire PDF — fixes the whole-document hang.
        """
        try:
            img = self._render_region(pdf_path, page_num, bbox, zoom=2.0)
            text = pytesseract.image_to_string(img).strip()
            return text
        except Exception as e:
            logger.error(f"OCR region failed page={page_num} bbox={bbox}: {e}")
            return ""

    def extract_lines_from_region(
        self,
        pdf_path: str,
        page_num: int,
        bbox: List[float],
        *,
        zoom: float = 2.0,
        lang: str = "eng",
    ) -> List[Dict[str, Any]]:
        """
        OCR a region and return lines with PDF-space bounding boxes.

        Uses Tesseract ``image_to_data`` for line-level coordinates, mapped back
        to the original PDF clip rect.
        """
        try:
            img = self._render_region(pdf_path, page_num, bbox, zoom=zoom)
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        except Exception as e:
            logger.error(f"OCR line extract failed page={page_num} bbox={bbox}: {e}")
            return []

        n = len(data.get("text") or [])
        if n == 0:
            return []

        grouped: Dict[tuple[int, int, int], List[int]] = defaultdict(list)
        for i in range(n):
            text = str(data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = int(float(data["conf"][i]))
            except (TypeError, ValueError):
                conf = -1
            if conf >= 0 and conf < 30:
                continue
            key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
            grouped[key].append(i)

        scale = 1.0 / float(zoom or 1.0)
        ox, oy = float(bbox[0]), float(bbox[1])
        out: List[Dict[str, Any]] = []

        for key in sorted(grouped.keys()):
            idxs = grouped[key]
            parts: List[str] = []
            x0s: List[float] = []
            y0s: List[float] = []
            x1s: List[float] = []
            y1s: List[float] = []
            for i in idxs:
                t = str(data["text"][i] or "").strip()
                if not t:
                    continue
                parts.append(t)
                left = float(data["left"][i]) * scale + ox
                top = float(data["top"][i]) * scale + oy
                width = float(data["width"][i]) * scale
                height = float(data["height"][i]) * scale
                x0s.append(left)
                y0s.append(top)
                x1s.append(left + width)
                y1s.append(top + height)
            if not parts:
                continue
            out.append(
                {
                    "text": " ".join(parts),
                    "bbox": [min(x0s), min(y0s), max(x1s), max(y1s)],
                }
            )

        out.sort(key=lambda it: (float(it["bbox"][1]), float(it["bbox"][0])))
        return out

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

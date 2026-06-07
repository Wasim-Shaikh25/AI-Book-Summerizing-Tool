"""Page-level OCR for scanned and two-up PDF spreads."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.utils.ocr_reader import OCRReader

logger = logging.getLogger(__name__)


def _page_text_char_count(page_dict: Dict[str, Any]) -> int:
    total = 0
    for block in page_dict.get("blocks") or []:
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            if not isinstance(line, dict):
                continue
            for span in line.get("spans") or []:
                if isinstance(span, dict):
                    total += len(str(span.get("text") or "").strip())
    return total


def _page_has_full_image(visuals: Sequence[Dict[str, Any]], *, min_area_ratio: float = 0.25) -> bool:
    for el in visuals:
        if el.get("kind") != "image":
            continue
        bbox = el.get("bbox") or []
        if len(bbox) != 4:
            continue
        w = float(bbox[2]) - float(bbox[0])
        h = float(bbox[3]) - float(bbox[1])
        if w * h > 0:
            return True
    return False


def is_scanned_page(
    page_dict: Dict[str, Any],
    visuals: Sequence[Dict[str, Any]],
    *,
    min_text_chars: int = 40,
) -> bool:
    """True when the page looks image-only or has very little extractable text."""
    if _page_text_char_count(page_dict) < min_text_chars:
        return True
    if _page_has_full_image(visuals):
        return _page_text_char_count(page_dict) < min_text_chars * 3
    return False


def split_page_regions(
    page_width: float,
    page_height: float,
    *,
    split_two_up: bool,
) -> List[Dict[str, Any]]:
    """Return OCR crop regions. Two-up mode splits at vertical center."""
    w = float(page_width or 0.0)
    h = float(page_height or 0.0)
    if w <= 0 or h <= 0:
        return [{"bbox": [0.0, 0.0, max(w, 1.0), max(h, 1.0)], "side": "full", "width": max(w, 1.0)}]

    if split_two_up:
        mid = w / 2.0
        return [
            {"bbox": [0.0, 0.0, mid, h], "side": "left", "width": mid},
            {"bbox": [mid, 0.0, w, h], "side": "right", "width": w - mid},
        ]
    return [{"bbox": [0.0, 0.0, w, h], "side": "full", "width": w}]


def virtual_page_number(pdf_page: int, region_index: int, *, split_two_up: bool) -> int:
    """Map PDF page + region to book page number when splitting two-up spreads."""
    if split_two_up and region_index >= 0:
        return (int(pdf_page) - 1) * 2 + region_index + 1
    return int(pdf_page)


def _synthetic_page_dict(
    *,
    ocr_lines: Sequence[Dict[str, Any]],
    page_number: int,
    region: Dict[str, Any],
    source_pdf_page: int,
) -> Dict[str, Any]:
    """Build a PyMuPDF-like page dict from OCR line bboxes."""
    page_w = float(region.get("width") or 0.0)
    page_h = float(region.get("bbox", [0, 0, 0, 0])[3]) - float(region.get("bbox", [0, 0, 0, 0])[1])
    if page_h <= 0:
        page_h = 842.0

    region_x0 = float((region.get("bbox") or [0, 0, 0, 0])[0])
    lines_block: List[Dict[str, Any]] = []
    for item in ocr_lines:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        bbox = item.get("bbox") or [0, 0, page_w, 12]
        if len(bbox) != 4:
            continue
        x0, y0, x1, y1 = [float(v) for v in bbox]
        # Normalize X into virtual page coordinates (left half starts at 0).
        nx0 = x0 - region_x0
        nx1 = x1 - region_x0
        lines_block.append(
            {
                "bbox": [nx0, y0, nx1, y1],
                "spans": [
                    {
                        "text": text,
                        "bbox": [nx0, y0, nx1, y1],
                        "size": 10.0,
                        "flags": 0,
                    }
                ],
            }
        )

    blocks: List[Dict[str, Any]] = []
    if lines_block:
        blocks.append({"type": 0, "lines": lines_block})

    return {
        "page_number": page_number,
        "source_pdf_page": source_pdf_page,
        "ocr_region": region.get("side") or "full",
        "width": page_w,
        "height": page_h,
        "blocks": blocks,
        "from_ocr": True,
    }


def apply_ocr_to_pages(
    pdf_path: str,
    pages: Sequence[Dict[str, Any]],
    visual_elements: Sequence[Dict[str, Any]],
    *,
    enabled: bool = True,
    mode: str = "auto",
    split_two_up: bool = False,
    min_text_chars: int = 40,
    zoom: float = 2.0,
    lang: str = "eng",
    tesseract_cmd: str = "",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Run page-level OCR on scanned pages (and optionally split two-up spreads).

    Returns (pages_for_layout, ocr_log).
    """
    mode = (mode or "auto").strip().lower()
    if not enabled or mode == "off":
        return list(pages), []

    visuals_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for el in visual_elements or []:
        pg = int(el.get("page_number") or 0)
        if pg:
            visuals_by_page.setdefault(pg, []).append(el)

    ocr = OCRReader(tesseract_cmd=tesseract_cmd or None)
    out_pages: List[Dict[str, Any]] = []
    ocr_log: List[Dict[str, Any]] = []

    for page_dict in pages:
        pdf_page = int(page_dict.get("page_number") or 0)
        page_w = float(page_dict.get("width") or 0.0)
        page_h = float(page_dict.get("height") or 0.0)
        page_visuals = visuals_by_page.get(pdf_page, [])

        scanned = is_scanned_page(page_dict, page_visuals, min_text_chars=min_text_chars)
        if mode == "auto" and not scanned:
            out_pages.append(page_dict)
            continue

        regions = split_page_regions(page_w, page_h, split_two_up=split_two_up)
        page_had_ocr = False
        for idx, region in enumerate(regions):
            try:
                ocr_lines = ocr.extract_lines_from_region(
                    pdf_path,
                    pdf_page,
                    region["bbox"],
                    zoom=zoom,
                    lang=lang,
                )
            except Exception as exc:
                logger.warning("OCR failed pdf_page=%s region=%s: %s", pdf_page, region.get("side"), exc)
                ocr_lines = []

            vpage = virtual_page_number(pdf_page, idx, split_two_up=split_two_up and len(regions) > 1)
            if ocr_lines:
                syn = _synthetic_page_dict(
                    ocr_lines=ocr_lines,
                    page_number=vpage,
                    region=region,
                    source_pdf_page=pdf_page,
                )
                out_pages.append(syn)
                page_had_ocr = True
                ocr_log.append(
                    {
                        "source_pdf_page": pdf_page,
                        "virtual_page": vpage,
                        "region": region.get("side"),
                        "line_count": len(ocr_lines),
                        "char_count": sum(len(str(l.get("text") or "")) for l in ocr_lines),
                        "status": "ok",
                    }
                )
            else:
                ocr_log.append(
                    {
                        "source_pdf_page": pdf_page,
                        "virtual_page": vpage,
                        "region": region.get("side"),
                        "line_count": 0,
                        "char_count": 0,
                        "status": "empty",
                    }
                )

        if not page_had_ocr:
            out_pages.append(page_dict)

    logger.info(
        "OCR stage: %d source pages -> %d layout pages (%d OCR runs logged)",
        len(pages),
        len(out_pages),
        len(ocr_log),
    )
    return out_pages, ocr_log

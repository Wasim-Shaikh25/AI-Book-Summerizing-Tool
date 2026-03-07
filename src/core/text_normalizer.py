from __future__ import annotations

from typing import Any, Dict, List

from .models import NormalizedLine


def normalize_text(pdf_extraction_result: Any) -> List[NormalizedLine]:
    """
    Phase: robust extraction.

    Deterministic text normalization for the clean pipeline.

    Input:
      The output of `extract_pdf`, which is:
        (lines_or_pages_data, book_title)

    Output:
      List[NormalizedLine] preserving page order and line order.
      ZERO text loss at line level.
    """
    # Already-normalized enriched lines (new pipeline path)
    if isinstance(pdf_extraction_result, tuple) and len(pdf_extraction_result) == 2:
        first = pdf_extraction_result[0]
    else:
        first = pdf_extraction_result

    if isinstance(first, list) and (len(first) == 0 or isinstance(first[0], NormalizedLine)):
        # Do not mutate, just return a list copy for safety.
        return list(first)

    # Legacy fallback: pages_data list[{"text": str, "page_number": int}]
    pages_data: List[Dict[str, Any]] = first

    out: List[NormalizedLine] = []
    line_id = 0
    for page in pages_data:
        page_text = page.get("text", "")
        page_number = page.get("page_number", None)
        for line in str(page_text).splitlines():
            # Create a minimal NormalizedLine for legacy callers
            out.append(
                NormalizedLine(
                    line_id=line_id,
                    text=line,
                    page_number=page_number,
                    y_pos=0.0,
                    page_height=0.0,
                    font_size=0.0,
                    is_bold=False,
                    x_center=0.0,
                    page_width=0.0,
                    vertical_gap_above=0.0,
                    is_link=False,
                    centered=False,
                    large_font=False,
                    large_gap=False,
                )
            )
            line_id += 1

    return out

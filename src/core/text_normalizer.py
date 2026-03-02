from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from .models import NormalizedLine


def normalize_text(pdf_extraction_result: Any) -> List[NormalizedLine]:
    """
    Phase: integration stabilization.

    Deterministic text normalization for the clean pipeline.

    Input:
      Currently expects the output of `extract_pdf`, which is:
        (pages_data, book_title)
      where pages_data is: List[{"text": str, "page_number": int}]

    Output:
      List[NormalizedLine] preserving page order and line order.
      No trimming beyond splitting into lines (ZERO text loss at line level).
    """
    # Handle already-normalized input (safety during transition)
    if isinstance(pdf_extraction_result, list) and (
        len(pdf_extraction_result) == 0 or isinstance(pdf_extraction_result[0], NormalizedLine)
    ):
        return list(pdf_extraction_result)

    pages_data: List[Dict[str, Any]]
    if isinstance(pdf_extraction_result, tuple) and len(pdf_extraction_result) == 2:
        pages_data = pdf_extraction_result[0]
    else:
        # Best-effort: if caller passed pages_data directly
        pages_data = pdf_extraction_result

    out: List[NormalizedLine] = []
    line_id = 0

    for page in pages_data:
        page_text = page.get("text", "")
        page_number = page.get("page_number", None)

        # Preserve empty lines: splitlines() drops trailing empty line; acceptable for now.
        # We avoid .strip() to prevent data loss.
        for line in str(page_text).splitlines():
            out.append(NormalizedLine(id=line_id, text=line, page_number=page_number))
            line_id += 1

    return out

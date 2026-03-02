import os
import re
import sys

# Allow running as: python scripts/test_text_normalizer.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.text_normalizer import PDFTextNormalizer
from src.utils.pdf_reader import PDFReader


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _word_count(text: str) -> int:
    if not text:
        return 0
    # Count word-like tokens (unicode letters/digits/underscore)
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def main() -> None:
    # Default project pdf folder is `reference_files/` in this repo
    reader = PDFReader(pdf_folder=os.path.join(PROJECT_ROOT, "reference_files"))
    pages_data, book_title = reader.read_all_pdfs()

    raw_lines = []
    for p in pages_data:
        t = p.get("text", "") or ""
        raw_lines.extend(str(t).splitlines())

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)
    normalized_text = str(result.get("text", ""))

    print(f"Book title: {book_title}")
    print(f"Total lines before: {len(raw_lines)}")
    print(f"Total lines after:  {_count_lines(normalized_text)}")
    print(f"Word count:         {_word_count(normalized_text)}")
    toc_region = result.get("toc_region")
    heading_metadata = result.get("heading_metadata", []) or []

    dup_indices = sorted([h.get("index") for h in heading_metadata if h.get("toc_duplicate")])

    print(f"TOC region:         {toc_region}")
    print(f"Duplicate headings: {dup_indices}")
    print(f"Headings scored:    {len(heading_metadata)}")
    print("-" * 60)
    print("First 120 lines (after normalization):")
    print("-" * 60)

    out_lines = normalized_text.splitlines()
    for i, line in enumerate(out_lines[:120], start=1):
        print(f"{i:03d}: {line}")

    print("-" * 60)
    print("Top 15 heading_score lines:")
    print("-" * 60)
    top15 = sorted(
        heading_metadata,
        key=lambda h: float(h.get("heading_score") or 0.0),
        reverse=True,
    )[:15]
    for h in top15:
        print(
            f"idx={h.get('index')}, score={h.get('heading_score')}, toc_dup={h.get('toc_duplicate')}: {h.get('line')}"
        )


if __name__ == "__main__":
    main()

import os
import sys

# Allow running as: python scripts/debug_verify_numeric_headings.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.text_normalizer import PDFTextNormalizer
from src.utils.pdf_reader import PDFReader


def main() -> None:
    reader = PDFReader(pdf_folder=os.path.join(PROJECT_ROOT, "reference_files"))
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    print("Book:", book_title)
    print("Total headings:", len(result["heading_metadata"]))
    print("=" * 60)

    for h in result["heading_metadata"]:
        idx = h["index"]
        print(
            f'IDX={idx}, '
            f'SCORE={float(h["heading_score"]):.3f}, '
            f'TEXT={result["lines"][idx]}'
        )


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import sys

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.core.local_structure.block_segmenter import BlockSegmenter
from src.core.local_structure.config import StructureThresholds
from src.core.local_structure.outline_analyzer import OutlineAnalyzer
from src.core.local_structure.text_cleaner import TextCleaner
from src.utils.pdf_reader import PDFReader


def main() -> None:
    reader = PDFReader(pdf_folder="reference_files")
    pages, _ = reader.read_all_pdfs(specific_file="law_of_tort.pdf")
    full_text = "\n\n".join(p["text"] for p in pages)

    cleaned = TextCleaner().clean(full_text)
    blocks = BlockSegmenter().segment(cleaned)

    thr = StructureThresholds()
    outline = OutlineAnalyzer(blocks, thr).detect_outline_regions()

    print("blocks:", len(blocks))
    print("outline_count:", len(outline))
    print()

    for i in range(min(60, len(blocks))):
        t = (blocks[i].text or "").replace("\n", " ")[:100]
        mark = "OUT" if i in outline else "   "
        print(f"{i:03d} {mark} wc={int(blocks[i].word_count):02d} | {t}")


if __name__ == "__main__":
    main()

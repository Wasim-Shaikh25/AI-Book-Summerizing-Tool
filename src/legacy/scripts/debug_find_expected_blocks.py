from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.core.local_structure.block_segmenter import BlockSegmenter
from src.core.local_structure.text_cleaner import TextCleaner
from src.utils.pdf_reader import PDFReader


KEYS = [
    "MODULE 1",
    "LAW OF TORTS",
    "1.1 Tort",
    "1.2 Distinction",
    "A. INTRODUCTION",
    "II. Damage",
    "Tort and crime",
]


def main() -> None:
    reader = PDFReader(pdf_folder="reference_files")
    pages, _ = reader.read_all_pdfs(specific_file="law_of_tort.pdf")
    full_text = "\n\n".join(p["text"] for p in pages)

    cleaned = TextCleaner().clean(full_text)
    blocks = BlockSegmenter().segment(cleaned)

    print("blocks:", len(blocks))
    # Show the first few blocks to see whether composite header splitting is happening.
    print("\nFIRST 12 BLOCKS:")
    for i in range(min(12, len(blocks))):
        print(f"  ({i}, {int(blocks[i].word_count)}, {blocks[i].text.replace(chr(10), ' ')[:160]})")

    for k in KEYS:
        hits = []
        for i in range(len(blocks)):
            t = (blocks[i].text or "")
            if k.lower() in t.lower():
                hits.append((i, int(blocks[i].word_count), t.replace("\n", " ")[:140]))
        print("\nKEY:", k, "hits:", len(hits))
        for h in hits[:10]:
            print(" ", h)


if __name__ == "__main__":
    main()

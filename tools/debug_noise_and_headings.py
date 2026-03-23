from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

# Allow running as a script: `python tools/debug_noise_and_headings.py`
# by ensuring project root is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.pdf_extractor import extract_pdf
from src.structure.noise_filter import mark_noise


def main() -> None:
    pdf = "src/debug/pdf_files/law_of_tort.pdf"

    lines, title = extract_pdf(pdf)
    print("title:", title)
    print("total_lines:", len(lines))

    pages = sorted({l.page_number for l in lines if l.page_number is not None})
    print("pages_count:", len(pages), "min:", (pages[0] if pages else None), "max:", (pages[-1] if pages else None))

    # Quick distribution check
    page_counts = Counter([l.page_number for l in lines if l.page_number is not None])
    print("page_line_counts_top5:", page_counts.most_common(5))

    # Noise
    _, noise_log = mark_noise(lines)
    print("noise_log_items:", len(noise_log))
    if noise_log:
        print("noise_log_sample:", noise_log[:10])

    # Raw "1.1" presence in extracted lines
    rx = re.compile(r"^\s*\d+\.\d+\b")
    raw_11 = [l for l in lines if rx.match(l.text or "")]
    print("raw_1_1_like_count:", len(raw_11))
    print("raw_1_1_like_sample:", [(l.page_number, l.line_id, (l.text or "")[:80]) for l in raw_11[:10]])


if __name__ == "__main__":
    main()

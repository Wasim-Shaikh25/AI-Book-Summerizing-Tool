import os
import re
import sys
from collections import Counter

# Allow running as: python scripts/debug_print_headings.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.text_normalizer import PDFTextNormalizer
from src.utils.pdf_reader import PDFReader


def _word_count(s: str) -> int:
    if not s:
        return 0
    return len(re.findall(r"\w+", s, flags=re.UNICODE))


def _in_toc_region(idx: int, toc_region) -> bool:
    if not toc_region:
        return False
    start, end = toc_region
    return int(start) <= idx <= int(end)


def _span_preview_word_count(lines: list[str], idx: int, stop_on_blank: bool = True, max_lines: int = 20) -> int:
    """
    Rough span preview: count words in subsequent lines until:
    - next blank line (default), or
    - max_lines reached
    This is diagnostic only (does NOT alter content, does NOT infer true structure).
    """
    wc = 0
    consumed = 0
    for j in range(idx + 1, min(len(lines), idx + 1 + max_lines)):
        s = (lines[j] or "").strip()
        if stop_on_blank and s == "":
            break
        wc += _word_count(s)
        consumed += 1
    return wc


def main() -> None:
    reader = PDFReader(pdf_folder=os.path.join(PROJECT_ROOT, "reference_files"))
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    lines = result.get("lines", []) or []
    heading_metadata = result.get("heading_metadata", []) or []
    toc_region = result.get("toc_region")

    # Frequency over entire document lines (exact match)
    freq = Counter([str(ln) for ln in lines])

    # Extract all heading candidates using heading_score threshold only
    # (debug only: intentionally permissive)
    candidates = [
        h for h in heading_metadata if float(h.get("heading_score") or 0.0) >= 0.50
    ]

    # Inspect in document order (not score order)
    candidates = sorted(candidates, key=lambda h: int(h.get("index") or 0))

    # Duplicate detection among candidates (case-insensitive normalized title)
    def norm_title(t: str) -> str:
        return " ".join((t or "").split()).strip().lower()

    cand_title_counts = Counter([norm_title(str(h.get("line", ""))) for h in candidates])

    print(f"Book title: {book_title}")
    print(f"TOC Region: {toc_region}")
    print(f"Total Lines: {len(lines)}")
    print(f"Total Heading Candidates (score>=0.65): {len(candidates)}")
    print(f"Unique Heading Titles: {len(set(norm_title(str(h.get('line',''))) for h in candidates))}")
    print("=" * 50)

    for h in candidates:
        idx = int(h.get("index"))
        text = str(h.get("line", ""))
        score = float(h.get("heading_score") or 0.0)

        prev_line = str(lines[idx - 1]) if idx - 1 >= 0 else ""
        next_line = str(lines[idx + 1]) if idx + 1 < len(lines) else ""

        appears_multiple_times = cand_title_counts[norm_title(text)] > 1
        frequency_in_doc = int(freq[text])

        heading_wc = _word_count(text)
        span_wc = _span_preview_word_count(lines, idx)

        print("=" * 50)
        print(f"IDX: {idx}")
        print(f"TEXT: {text}")
        print(f"SCORE: {score}")
        print(f"WORD_COUNT: {heading_wc}")
        print(f"FREQUENCY_IN_DOC: {frequency_in_doc}")
        print(f"APPEARS_MULTIPLE_TIMES: {appears_multiple_times}")
        print(f"IN_TOC_REGION: {_in_toc_region(idx, toc_region)}")
        print(f"SPAN_PREVIEW_WORD_COUNT: {span_wc}")
        print(f"PREV_LINE: {prev_line}")
        print(f"NEXT_LINE: {next_line}")
        print("-" * 50)

    # Summary metrics
    scores = sorted([float(h.get("heading_score") or 0.0) for h in heading_metadata])
    top10 = sorted(heading_metadata, key=lambda x: float(x.get("heading_score") or 0.0), reverse=True)[:10]
    low10 = sorted(heading_metadata, key=lambda x: float(x.get("heading_score") or 0.0))[:10]

    print("\nSUMMARY")
    print(f"Total Lines: {len(lines)}")
    print(f"Total Heading Candidates (score>=0.65): {len(candidates)}")
    print(f"Unique Heading Titles: {len(set(norm_title(str(h.get('line',''))) for h in candidates))}")
    print(f"TOC Region: {toc_region}")

    print("\nTop 10 Highest Scores:")
    for h in top10:
        print(f"  idx={h.get('index')}, score={h.get('heading_score')}: {h.get('line')}")

    print("\nTop 10 Lowest Scores:")
    for h in low10:
        print(f"  idx={h.get('index')}, score={h.get('heading_score')}: {h.get('line')}")


if __name__ == "__main__":
    main()

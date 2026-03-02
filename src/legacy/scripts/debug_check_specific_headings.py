import os
import re
import sys

# Allow running as: python scripts/debug_check_specific_headings.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.text_normalizer import PDFTextNormalizer
from src.utils.pdf_reader import PDFReader


def _word_count(s: str) -> int:
    if not s:
        return 0
    return len(re.findall(r"\w+", s, flags=re.UNICODE))


def _uppercase_ratio(s: str) -> float:
    letters = [ch for ch in (s or "") if ch.isalpha()]
    if not letters:
        return 0.0
    upp = sum(1 for ch in letters if ch.isupper())
    return upp / max(1, len(letters))


def _has_number_prefix(s: str) -> bool:
    return bool(re.match(r"^\s*\d+(\.\d+)*\b", s or ""))


def _in_toc_region(idx: int, toc_region) -> bool:
    if not toc_region:
        return False
    start, end = toc_region
    return int(start) <= idx <= int(end)


def _feature_breakdown(line: str) -> dict:
    s = line or ""
    stripped = s.strip()
    return {
        "word_count": _word_count(stripped),
        "has_number_prefix": _has_number_prefix(stripped),
        "has_colon": ":" in stripped,
        "ends_with_period": stripped.endswith("."),
        "uppercase_ratio": round(_uppercase_ratio(stripped), 3),
        "comma_count": stripped.count(","),
        "length": len(stripped),
    }


def main() -> None:
    reader = PDFReader(pdf_folder=os.path.join(PROJECT_ROOT, "reference_files"))
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    lines = result.get("lines", []) or []
    heading_metadata = result.get("heading_metadata", []) or []
    toc_region = result.get("toc_region")

    # Build quick lookup from heading_metadata by index
    score_by_idx = {int(h.get("index")): float(h.get("heading_score") or 0.0) for h in heading_metadata}

    needles = [
        ("1.1 Tort:", "1.1 Tort:"),
        ("1.2 Distinction from Crime", "1.2 Distinction from Crime"),
    ]

    print(f"Book title: {book_title}")
    print(f"TOC Region: {toc_region}")
    print(f"Total Lines: {len(lines)}")
    print(f"Total headings in heading_metadata: {len(heading_metadata)}")
    print("=" * 50)

    # Since we removed duplicate deletion/marking, this is always False.
    filtered_by_duplicate_logic = False

    for label, contains_text in needles:
        found_any = False
        for idx, ln in enumerate(lines):
            if contains_text in (ln or ""):
                found_any = True
                text = str(ln)
                score = float(score_by_idx.get(idx, 0.0))

                print("=" * 50)
                print("LINE FOUND")
                print(f"QUERY: {label}")
                print(f"IDX: {idx}")
                print(f"TEXT: {text}")
                print(f"HEADING_SCORE: {score}")
                print(f"PASSED_THRESHOLD_0.65: {score >= 0.65}")
                print(f"PASSED_THRESHOLD_0.50: {score >= 0.50}")
                print(f"FILTERED_BY_DUPLICATE_LOGIC: {filtered_by_duplicate_logic}")
                print(f"IN_TOC_REGION: {_in_toc_region(idx, toc_region)}")
                print("FEATURES:")
                feats = _feature_breakdown(text)
                for k, v in feats.items():
                    print(f"  - {k}: {v}")
                print("=" * 50)

        if not found_any:
            print("=" * 50)
            print("LINE NOT FOUND")
            print(f"QUERY: {label}")
            print("=" * 50)

    # Print top 30 heading lines by score so we can see ranking.
    # Note: heading_metadata only includes lines that the normalizer already classified as probable headings.
    top30 = sorted(
        heading_metadata,
        key=lambda h: float(h.get("heading_score") or 0.0),
        reverse=True,
    )[:30]

    print("\nTOP 30 HEADING LINES BY SCORE (desc)")
    for h in top30:
        idx = int(h.get("index"))
        print(f"idx={idx}, score={h.get('heading_score')}: {h.get('line')}")


if __name__ == "__main__":
    main()

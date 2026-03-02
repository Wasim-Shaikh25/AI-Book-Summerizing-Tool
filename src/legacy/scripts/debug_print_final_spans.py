import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.pdf_reader import PDFReader
from src.core.text_normalizer import PDFTextNormalizer
from src.structure.raw_span_builder import build_raw_spans, RawSpan
from src.structure.span_merger import merge_invalid_spans


def _word_count(lines: list[str]) -> int:
    return sum(len((ln or "").split()) for ln in lines)


def main():
    reader = PDFReader(pdf_folder="reference_files")
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    lines = result["lines"]
    heading_metadata = result.get("heading_metadata", [])
    heading_indices = sorted(int(h["index"]) for h in heading_metadata if "index" in h)

    raw_spans = build_raw_spans(lines, heading_indices)

    # NOTE: This is only a diagnostic. Replace this validation_map with actual LLM results.
    validation_map = {}
    for s in raw_spans:
        # Heuristic: very long titles are likely not headings
        validation_map[s.span_id] = len((s.heading_text or "").split()) <= 12

    merged_spans = merge_invalid_spans(raw_spans, validation_map)

    print("Book:", book_title)
    print("Raw spans:", len(raw_spans))
    print("Merged spans:", len(merged_spans))
    print("=" * 60)

    for fragment_id, span in enumerate(merged_spans, start=1):
        # Attach diagnostic properties without mutating dataclass definition
        title = (span.heading_text or "").strip()
        words = _word_count(span.content_lines)

        print("=" * 60)
        print(f"Fragment ID: {fragment_id}")
        print(f"Title: {title}")
        print(f"Words: {words}")
        print()


if __name__ == "__main__":
    main()

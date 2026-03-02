from src.utils.pdf_reader import PDFReader
from src.core.text_normalizer import PDFTextNormalizer
from src.structure.heading_span_builder import HeadingSpanBuilder
from src.core.ai.heading_batcher import HeadingCandidate, build_heading_batches


def _words_preview(text: str, max_words: int = 120) -> str:
    parts = text.split()
    return " ".join(parts[:max_words])


def main():
    reader = PDFReader(pdf_folder="reference_files")
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    lines = result["lines"]
    heading_metadata = result["heading_metadata"]

    # Stage 1: spans (deterministic)
    builder = HeadingSpanBuilder()
    spans = builder.build_spans(lines, heading_metadata)

    # NOTE: Merge-invalid-spans step should happen inside LocalStructureEngine.
    # This debug script assumes spans are already stable and just assigns fragment_id sequentially.
    candidates = []
    for fragment_id, s in enumerate(spans, start=1):
        start = int(s["start_index"])
        end = int(s["end_index"])
        preview_text = " ".join(lines[start + 1 : end + 1]).strip()
        candidates.append(
            HeadingCandidate(
                fragment_id=fragment_id,
                index=int(s["start_index"]),
                title=str(s["title"]).strip(),
                span_word_count=int(s["span_word_count"]),
                span_line_count=int(s["span_line_count"]),
                span_preview=_words_preview(preview_text, max_words=120),
            )
        )

    batches = build_heading_batches(document_title=book_title, candidates=candidates)

    print("Book:", book_title)
    print("=" * 80)
    print(f"Total candidates: {len(candidates)}")
    print(f"Total batches: {len(batches)}")
    print("=" * 80)

    for b in batches:
        payload = b.to_payload()
        print(f"\nBATCH {b.batch_id} (size={len(b.headings)})")
        print("-" * 80)
        first = b.headings[0]
        last = b.headings[-1]
        print(f"Fragment range: {first.fragment_id} -> {last.fragment_id}")
        print(f"Index range: {first.index} -> {last.index}")
        print("Payload keys:", list(payload.keys()))
        print("Payload headings:", len(payload["headings"]))
        # Print first 2 headings as sanity check
        for h in payload["headings"][:2]:
            print(
                f'  id={h["id"]} idx={h["index"]} words={h["span_word_count"]} '
                f'title="{h["title"][:80]}"'
            )


if __name__ == "__main__":
    main()

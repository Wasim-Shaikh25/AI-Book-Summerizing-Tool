from src.utils.pdf_reader import PDFReader
from src.core.text_normalizer import PDFTextNormalizer
from src.structure.heading_span_builder import HeadingSpanBuilder
from src.structure.structural_judge_qwen import build_judge_payload, run_structural_judge


def main():
    reader = PDFReader(pdf_folder="reference_files")
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    lines = result["lines"]
    headings = result["heading_metadata"]

    builder = HeadingSpanBuilder()
    spans = builder.build_spans(lines, headings)

    payload = build_judge_payload(
        document_title=book_title,
        spans=spans,
        lines=lines,
    )

    judged = run_structural_judge(payload)

    id_to_title = {h["id"]: h["title"] for h in payload["headings"]}
    id_to_index = {h["id"]: h["index"] for h in payload["headings"]}
    id_to_span = {h["id"]: h["span_word_count"] for h in payload["headings"]}

    print("Book:", book_title)
    print("=" * 80)
    print("STRUCTURAL JUDGE OUTPUT (VALID JSON)")
    print("=" * 80)

    for item in sorted(judged["validated_headings"], key=lambda x: id_to_index[x["id"]]):
        hid = item["id"]
        title = id_to_title.get(hid, "")
        print(
            f"[id={hid} idx={id_to_index.get(hid)} level={item['level']} "
            f"valid={item['is_valid']} toc_dup={item['is_toc_duplicate']} "
            f"parent={item['parent_id']} span_words={id_to_span.get(hid)}]\n"
            f"  {title}"
        )
        print("-" * 80)


if __name__ == "__main__":
    main()

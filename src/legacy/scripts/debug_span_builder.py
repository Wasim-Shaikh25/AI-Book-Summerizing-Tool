from src.utils.pdf_reader import PDFReader
from src.core.text_normalizer import PDFTextNormalizer
from src.structure.heading_span_builder import HeadingSpanBuilder

reader = PDFReader(pdf_folder="reference_files")
pages_data, book_title = reader.read_all_pdfs()

normalizer = PDFTextNormalizer()
result = normalizer.normalize(pages_data)

lines = result["lines"]
headings = result["heading_metadata"]

builder = HeadingSpanBuilder()
spans = builder.build_spans(lines, headings)
filtered = builder.filter_structural_headings(spans)

print("Book:", book_title)
print("=" * 60)
print("ALL SPANS:")
print("=" * 60)

for s in spans:
    print(
        f'{s["title"]}\n'
        f'  Words: {s["span_word_count"]}, '
        f'Lines: {s["span_line_count"]}, '
        f'NonEmpty: {s["span_non_empty_count"]}'
    )
    print("-" * 40)

print("\nSTRUCTURAL HEADINGS:")
print("=" * 60)

for s in filtered:
    print(f'{s["title"]} ' f'(Words={s["span_word_count"]})')

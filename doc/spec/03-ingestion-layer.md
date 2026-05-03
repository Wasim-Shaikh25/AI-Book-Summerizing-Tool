# 03 — Ingestion layer

## `extract_pdf` → tuple passed to `normalize_text`

**File:** `src/ingestion/pdf_extractor.py`

```
extract_pdf(pdf_path) -> (List[NormalizedLine], book_title: str)
  → PDFReader.read_all_pdfs(specific_file=...)   # filename-based title (compat)
  → _pymupdf_extract_pages_dict(pdf_path)
  → enrich_layout_from_pymupdf_pages(pages_dict)  # src/ingestion/layout_enrichment.py
  → return (enriched_lines, book_title)
```

**Downstream:** `normalize_text(pdf_extraction_result)` in `src/ingestion/text_normalizer.py` unwraps the tuple, returns `List[NormalizedLine]` (copy) when the first element is already enriched lines.

## Layout enrichment for logging / page lookup

**File:** `src/ingestion/layout_enrichment.py`

```
lines_to_log(lines: Iterable[NormalizedLine]) -> List[Dict]
  → used by run_pipeline for 01_layout_lines.json and layout_by_line_id[line_id]
```

Supporting internals include `_extract_lines_from_page_dict`, `enrich_layout_from_pymupdf_pages` (if used by extractor path), bold/center inference helpers.

## Optional thin API

**File:** `src/ingestion/service.py`

```
ingest_pdf(file_path) -> IngestedPdf
  → extract_pdf(file_path)
  → IngestedPdf(pdf=..., page_count=...)
```

Not used by `run_pipeline` (which calls `extract_pdf` directly).

## Utilities

- `src/utils/pdf_reader.py` — `PDFReader` class (separate from main pipeline path unless imported elsewhere).
- `src/utils/ocr_reader.py` — `OCRReader` for alternate input paths.

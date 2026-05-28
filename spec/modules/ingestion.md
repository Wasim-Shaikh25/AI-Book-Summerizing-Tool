# Module: Ingestion

> Code package: `src/ingestion/`  
> Legacy: `doc/spec/03-ingestion-layer.md`

## Purpose

Convert PDF files into layout-enriched, normalized line streams including tables and OCR text.

## Public APIs

| Function | Module | Output |
|----------|--------|--------|
| `extract_pdf(pdf_path)` | `pdf_extractor.py` | lines, book_title, visual_elements |
| `normalize_text(result)` | `text_normalizer.py` | `List[NormalizedLine]` |
| `lines_to_log(lines)` | `layout_enrichment.py` | layout JSON payload |
| `ingest_pdf(file_path)` | `service.py` | `IngestedPdf` |

## Dependencies

- PyMuPDF (`fitz`) via `pdf_extractor`
- `src/utils/pdf_reader.py`, `src/utils/ocr_reader.py` for OCR fallback
- `src/core/models.NormalizedLine`

## Outputs

- Normalized lines with typography, position, noise flags (initially false)
- Visual elements dict (tables, images, diagrams) for stage logging

# Requirements: OCR Stage for Scanned / Two-Up PDFs

## Problem

Scanned PDFs (especially two book pages on one PDF page) often have no extractable text layer. The current pipeline skips full-page OCR, producing empty or jumbled lines.

## Functional Requirements

1. Detect pages with insufficient extractable text (`auto` mode).
2. Run Tesseract OCR on full-page or split regions when enabled.
3. Optional **two-up split**: crop left/right halves and OCR separately with correct reading order.
4. Map OCR lines into synthetic page dicts consumed by existing layout enrichment.
5. Configurable via `config/default.yaml` and environment variables.

## Non-Functional

- `auto` mode must not OCR digital text PDFs (performance).
- Graceful fallback when Tesseract is unavailable (keep original page, log warning).
- Virtual page numbers for two-up: left = `(pdf_page-1)*2+1`, right = `(pdf_page-1)*2+2`.

## Impacted Modules

- `src/modules/ingestion/pdf_extractor.py`
- `src/modules/ingestion/ocr_stage.py` (new)
- `src/utils/ocr_reader.py`
- `src/modules/ingestion/layout_enrichment.py` (Y-then-X sort)

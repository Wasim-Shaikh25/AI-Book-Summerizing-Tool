# Module: Export

> Code package: `src/export/`

## Purpose

Format pipeline output for terminal display and Word `.docx` export via Pandoc.

## Public APIs

| Class | Module | Methods |
|-------|--------|---------|
| `WordExporter` | `word_exporter.py` | `structured_text_to_word`, `assemble_full_book_structured_text` |
| `OutputManager` | `output_manager.py` | `format_for_terminal`, `export_to_word`, `handle_output` |

## Dependencies

- `reference.docx` template at project root (`REFERENCE_DOCX_PATH`)
- Output directory: `output/` (`OUTPUT_FOLDER`)
- Pandoc (external) for docx assembly

## Status

Export handler in CLI is stubbed; direct use via `OutputManager` / scripts is supported.

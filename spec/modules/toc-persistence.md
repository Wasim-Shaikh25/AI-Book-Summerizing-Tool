# Module: TOC & Persistence

> Code: `src/structure/toc_*`, `src/storage/`  
> Legacy: `doc/spec/05-deterministic-toc-persistence.md`

## Purpose

Detect repeated TOC patterns, tag book metadata, clean final heading sets, and optionally persist to SQLite.

## TOC Functions

| Function | Module |
|----------|--------|
| `detect_deterministic_toc` | `toc_repeat_detection.py` |
| `build_toc_sections_from_repeated_headings` | `toc_repeat_detection.py` |
| `book_metadata_from_first_toc_section` | `toc_repeat_detection.py` |
| `clean_toc` | `toc_cleaning.py` |
| `split_toc_forward_only` | `toc_splitter.py` |

## Persistence

Triggered when `run_pipeline(..., persist_to_db=True)`:

- `KnowledgeStore.save_pipeline_artifact`
- `BookRepository.save_book`
- `TocRepository.save_full_toc` (fragments, headings, links)
- `TopicRepository` for topic records

## Outputs

- `final_headings` with `is_toc` / `in_toc_section` stripped for consumer-facing lists
- SQLite rows in knowledge store schema

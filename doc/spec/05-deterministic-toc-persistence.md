# 05 — Deterministic TOC, metadata, DB persistence

## Repeat-based TOC detection

**File:** `src/structure/toc_repeat_detection.py`

Call order from `run_pipeline`:

```
detect_deterministic_toc(lines, toc_out)
  → returns (toc_seed_ids: Set[int], seed_log_items)
  → uses _norm, _looks_like_numbered_outline_line (guards chain false-positives on page 1)
  → uses _heading_line_id / heading text helpers

build_toc_sections_from_repeated_headings(lines, toc_out)
  → returns (toc_section_line_ids, section_log_items)

book_metadata_from_first_toc_section(lines, det_section_log)
  → returns (book_metadata_line_ids: Set[int], book_meta_log)
```

Effects on headings: `FinalHeading.is_toc` and `FinalHeading.in_toc_section` set on matching line ids.

## JSON outputs (when logging enabled)

- `09_final_headings.json` — all headings with flags.
- `12_final_headings_2.json` — **minus** TOC rows, TOC-section rows, and book-metadata line ids (`_final_headings_without_toc_and_metadata` in `pipeline.py`).
- `10_deterministic_toc.json` — merged seed + section log items.
- `11_book_metadata.json` — metadata span log.

## `persist_to_db=True` branch

**Inside** `run_pipeline` after `PipelineResult` construction:

```
KnowledgeStore()
BookRepository.save_book(BookMetadata(title=stem, ...))
TocRepository.save_full_toc(
    book_id,
    final_headings=result.final_headings,
    fragments=result.fragments,
    heading_to_fragment_id=...,
    clear_existing=True,
)
# Then mirror stage JSON files into DB via store.save_pipeline_artifact(...)
```

**Files:** `src/storage/knowledge_store.py`, `src/storage/book_repository.py`, `src/storage/toc_repository.py`, `src/storage/schema.py`.

## Offline TOC split (optional)

You can call `src/structure/toc_splitter.write_toc_split_outputs` from a small script against a run folder; nothing in-repo wires it to the pipeline.

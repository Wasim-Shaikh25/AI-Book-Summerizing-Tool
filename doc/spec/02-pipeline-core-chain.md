# 02 — `run_pipeline` core chain

**Module:** `src/core/pipeline.py`  
**Entry:** `run_pipeline(pdf_path, *, enable_logs=False, persist_to_db=False)`

## Logger construction

```
PipelineLogger.create(pdf_file=..., enabled=enable_logs)
  → if enabled: real PipelineLogger with logs/run_<utc>/
  → else: NoOpPipelineLogger (no disk writes)
```

## Linear stage chain (same order as source)

```
1. extract_pdf(pdf_path)
     → src/ingestion/pdf_extractor.py — returns (List[NormalizedLine], book_title)

2. normalize_text(pdf_doc)
     → src/ingestion/text_normalizer.py — unwraps tuple; returns List[NormalizedLine]

3. lines_to_log(lines)
     → src/ingestion/layout_enrichment.py — layout payload for JSON + layout_by_line_id map
     → logger.write_stage("layout_lines", ...)

4. mark_noise(lines)
     → src/structure/noise_filter.py — mutates/returns lines + noise log
     → logger.write_stage("noise_filter", ...)

5. collect_candidates_scored(lines)
     → src/structure/candidate_scoring.py — scored HeadingCandidate list + scoring log
     → logger.write_stage("candidate_scoring", ...)

6. gate_heading_validity_candidates(candidates, lines=lines)
     → src/structure/heading_validity_gate.py — filters candidates + gate log
     → logger.write_stage("heading_validity_gate", ...) → `03b_heading_validity_gate.json`

7. apply_continuity_filter(candidates, layout_by_line_id)
     → src/structure/continuity_filter.py — builds List[FinalHeading] (same rules as former inline loop)
     → optional logger.write_stage("continuity_filter", dropped_continuity_log)

8. build_fragments(lines, headings)
     → src/structure/fragments.py — fragments_result + fragments log
     → logger.write_stage("fragments", ...)
     → patch heading.fragment_id from heading_to_fragment_id

9. clean_toc(final_heads, fragments=...)
     → src/structure/toc_cleaning.py — returns toc_out (list of FinalHeading)

10. Deterministic TOC + sections + metadata
     → detect_deterministic_toc(lines, toc_out)
          → src/structure/toc_repeat_detection.py — seed line ids; mutates h.is_toc
     → build_toc_sections_from_repeated_headings(lines, toc_out)
          → mutates h.in_toc_section
     → book_metadata_from_first_toc_section(lines, det_section_log)
          → book_metadata_line_ids + book_meta_log

11. Build final_headings_items (dict rows incl. page_number from layout)
     → logger.write_stage("final_headings", ...)
     → logger.write_stage("final_headings_2", _final_headings_without_toc_and_metadata(...))
     → logger.write_stage("deterministic_toc", det_toc_log_items)
     → logger.write_stage("book_metadata", book_meta_log)

12. Return PipelineResult(final_headings=toc_out, fragments, heading_to_fragment_id)

13. If persist_to_db:
     → KnowledgeStore(), BookRepository, TocRepository
     → book_repo.save_book(BookMetadata(...))
     → repo.save_full_toc(...)
     → store.save_pipeline_artifact(...) per existing stage JSON file (if logger wrote them)
```

## Private helpers in this module

- `_final_headings_without_toc_and_metadata` — strips TOC/metadata rows for `12_final_headings_2.json`.
- `_parse_line_id_from_heading_id` — parses `L<line_id>:...` style ids.

## Related types

- `FinalHeading`, `PipelineResult` — `src/core/models.py`.

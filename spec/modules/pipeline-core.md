# Module: Pipeline Core

> Code: `src/modules/pipeline/runner.py`  
> Legacy: `doc/spec/02-pipeline-core-chain.md`

## Purpose

Single production orchestrator for deterministic book structure extraction, optional stage logging, and optional SQLite persistence.

## Public API

```python
run_pipeline(pdf_path, *, enable_logs=False, persist_to_db=False)
  → (PipelineResult, PipelineLogger | None)
```

## Stage Chain

1. `extract_pdf` → `normalize_text`
2. Layout log (`lines_to_log`)
3. Visual elements log
4. `mark_noise`
5. `collect_candidates_scored`
6. `gate_heading_validity_candidates`
7. `apply_continuity_filter`
8. `build_fragments` + patch heading `fragment_id`
9. `clean_toc`
10. Deterministic TOC + metadata (`toc_repeat_detection`)
11. Optional Stage 15b doubted-section resolver
12. Optional DB persist
13. Return `PipelineResult`

## Dependencies

- All `src/ingestion/*` and `src/structure/*` stage modules
- `src/structure/logging/pipeline_logger.py`
- `src/storage/*` when `persist_to_db=True`

## Internal Helpers

- `_final_headings_without_toc_and_metadata()` — strips TOC/metadata rows from output

# 06 — Logging, debug trace, visualization

## PipelineLogger

**File:** `src/structure/logging/pipeline_logger.py`

```
PipelineLogger.create(pdf_file=..., enabled=True)
  → run_dir = logs/run_<YYYY-MM-DD_HH-MM-SS>/

PipelineLogger.write_stage(stage_name, items)
  → maps stage_name → fixed filename (01_… through 12_…, decision_trace)
  → _envelope(...) wraps { run_id, stage, pdf_file, timestamp, total_items, items }
```

`NoOpPipelineLogger` — same interface; no writes when `enabled=False`.

## Debug runner

**File:** `src/debug/run_toc_trace.py`

```
run(pdf_path)
  → run_pipeline(pdf_abs, enable_logs=True, persist_to_db=True)
  → returns logger.run_dir

__main__:
  → run(pdf)
  → _write_latest_run_pointer(run_dir)   # logs/LATEST_RUN.txt
  → _print_deterministic_toc_summary(run_dir)
  → optional: visualize_run(...) if --visualize
  → optional: _open_in_file_manager if --open-folder
```

## Visualizer

**File:** `src/debug/visualizer.py`

```
visualize_run(pdf_path=..., run_dir=...)
  → _load_json for layout, noise, fragments, final_headings, deterministic_toc, book_metadata
  → _index_layout_boxes, _collect_*_line_ids helpers
  → _draw_boxes → writes visualization.pdf under run_dir
```

Layering order (conceptually): layout boxes, noise, fragments, TOC spans, headings, book metadata (see module docstring / draw order in source).

# Module: Logging & Debug

> Code: `src/structure/logging/`, `src/debug/`  
> Legacy: `doc/spec/06-logging-debug-visualization.md`

## Purpose

Whitelisted stage JSON logging and PDF visualization for pipeline debugging.

## PipelineLogger

- `PipelineLogger.create(pdf_file, enabled)` → real logger or `NoOpPipelineLogger`
- Writes to `logs/run_<utc>/` when enabled
- `write_stage(name, payload)` — whitelisted stage filenames only

## Debug Tools

| Tool | Entry | Behavior |
|------|-------|----------|
| TOC trace | `python -m src.debug.run_toc_trace <pdf>` | Runs pipeline with logs + DB |
| Visualizer | `visualize_run(pdf_path, run_dir)` | Annotated debug PDF from stage JSON |

## Dependencies

- Stage payloads from `run_pipeline` when `enable_logs=True`
- PyMuPDF for visualization overlay

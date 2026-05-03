# 00 — Overview

## Purpose

End-to-end flow: **ingest PDF** → **normalize lines** → **detect heading candidates** → **filters** → **fragments** → **TOC cleanup** → **deterministic TOC + book metadata tagging** → **optional SQLite persistence** and **optional JSON run logs**.

## Top-level entry points

1. **`main.py`**
   - `main()` → `CommandLoop().start()` (`src/interaction/command_loop.py`).

2. **Pipeline (canonical import for traces)**
   - `from src.book_pipeline import run_pipeline` re-exports `src.core.pipeline.run_pipeline`.

3. **Debug TOC trace**
   - `python -m src.debug.run_toc_trace` or `python src/debug/run_toc_trace.py <pdf> [--visualize] [--open-folder]`
   - `run()` → `run_pipeline(..., enable_logs=True, persist_to_db=True)` (`src/debug/run_toc_trace.py`).

## Core orchestration

- **`src/core/pipeline.py` — `run_pipeline(pdf_path, enable_logs=..., persist_to_db=...)`**
  - Single production orchestrator for structure extraction + logging + optional DB.

## Domain models (representative)

| Symbol | Module | Role |
|--------|--------|------|
| `NormalizedLine` | `src/core/models.py` | One text line + layout flags after normalization |
| `HeadingCandidate` | same | Pre-final heading proposal |
| `FinalHeading` | same | Heading after continuity + TOC passes; may carry `is_toc`, `in_toc_section` |
| `Fragment` | same | Text block between headings |
| `PipelineResult` | same | `final_headings`, `fragments`, `heading_to_fragment_id` |

## Package map (`src/`)

| Area | Path | Role |
|------|------|------|
| Core | `src/core/` | `run_pipeline`, models |
| Ingestion | `src/ingestion/` | PDF → lines, layout enrichment |
| Structure | `src/structure/` | Scoring, noise, gates, fragments, TOC, deterministic TOC |
| Storage | `src/storage/` | SQLite schema + repositories |
| Interaction | `src/interaction/` | CLI loop, command parser, handlers (partially legacy) |
| (removed) | — | LLM adaptor and LLM-only structure modules were deleted; pipeline is deterministic only |
| Debug | `src/debug/` | Trace runner, PDF visualization |
| Export | `src/export/` | Word export |
| Generation | `src/generation/` | Rewrite engine (optional; not wired from CLI ingestion) |

## Note on duplicate modules

- `src/core/candidate_scoring.py` exists alongside `src/structure/candidate_scoring.py`. **`run_pipeline` imports `collect_candidates_scored` from `src.structure.candidate_scoring`** only.

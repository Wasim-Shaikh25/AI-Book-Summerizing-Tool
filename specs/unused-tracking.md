# Unused / Dead Code Tracking

> MESO Rule 7: After every change, detect unused code. Remove if safe, otherwise log here.

---

## 1. Removed (2026-06-01 cleanup)

| Path | Reason removed |
|------|----------------|
| `src/interaction/`, `src/ingestion/`, `src/storage/`, `src/structure/`, `src/generation/`, `src/debug/`, `src/export/`, `src/core/` | Legacy MESO compat shims — zero runtime imports |
| `src/app/`, `src/domain/` | Empty / unused re-export shims |
| `doc/spec/` | Superseded by authoritative `/spec` |
| `src/modules/generation/content_generation.py` | Placeholder, never imported |
| `src/modules/ingestion/service.py` | `ingest_pdf` never wired |
| `src/modules/interaction/handlers/question_paper_handler.py` | Stub, never imported |
| `src/modules/storage/topic_repository.py` | Only used by removed question paper handler |
| `src/modules/structure/toc_splitter.py` | Utility never called from pipeline |

---

## 2. Currently Active (reference)

| Path | Role |
|------|------|
| `src/modules/**` | Canonical feature code |
| `src/shared/**` | Config, models, errors |
| `src/config.py` | Shim to `shared.config` (widely imported) |
| `src/book_pipeline/` | Stable alias for `run_pipeline` |
| `backend/**` | Web API layer |
| `frontend/**` | Web UI layer |

---

## 3. Removed (2026-06-07 cleanup)

| Path / symbol | Reason removed |
|---------------|----------------|
| `pipeline_logger.py` legacy slots `04_*`, `05_*`, `06_*`, `08_hierarchy`, `decision_trace` | Never written by live pipeline |
| `pipeline_logger.record_decision()`, `write_json()` | Zero callers |
| `heading_validity_gate.gate_toc_candidates()` | Unwired; superseded by `toc_repeat_detection` |
| `toc_cleaning.py` dedupe/trace helpers | Unreachable; `clean_toc` is identity pass |
| `shared/models.HeadingGateTraceRecord` | Zero imports |
| `rag/service.ensure_rag_index()`, `hybrid_retrieve_sections()` | Dead wrappers; use `RagService` |
| `rag/__init__.py` broken `hybrid_retrieve` export | Fixed to `RagService` only |
| `export_handler.py` merged import typo | Blocked CLI import |

**Renamed:** stage log keys `doubted_resolved` → `15b_doubted_resolved`, `revalidation` → `15b_revalidation`.

**Consolidated:** `pipeline/stage_registry.py` — single source for stage log keys and artifact filenames.

**Deferred (still active):** `heading_heuristics.py` — used by unit tests; wire into gate or keep.

---

## 4. Detection Policy

- Run `pytest` on every change.
- Grep for imports before deleting modules.
- Log deferred removals here with target date.

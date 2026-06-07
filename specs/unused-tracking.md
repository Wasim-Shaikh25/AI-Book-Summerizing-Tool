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

## 3. Detection Policy

- Run `pytest` on every change.
- Grep for imports before deleting modules.
- Log deferred removals here with target date.

# Architecture — AI Notes Creator Model

> Authority: structural changes MUST update this file BEFORE code (MESO Rule 6).

---

## 1. Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Presentation     │ CLI (CommandLoop)  │  Debug trace     │
├─────────────────────────────────────────────────────────────┤
│  Application      │ modules/pipeline/runner.py              │
│                   │ Intent handlers (rewrite, export, Q&A)  │
├─────────────────────────────────────────────────────────────┤
│  Shared           │ shared/models.py, shared/config.py      │
├─────────────────────────────────────────────────────────────┤
│  Modules          │ ingestion │ structure │ storage │ …   │
│  (mirror /spec)   │ generation │ export │ interaction     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Pipeline Stage Order

Authoritative order in `src/modules/pipeline/runner.py`:

1. `extract_pdf` → `normalize_text`
2. `lines_to_log` (layout payload)
3. `mark_noise`
4. `collect_candidates_scored`
5. `gate_heading_validity_candidates`
6. `apply_continuity_filter`
7. `build_fragments` + patch `fragment_id` on headings
8. `clean_toc`
9. Deterministic TOC: `detect_deterministic_toc`, `build_toc_sections_from_repeated_headings`, `book_metadata_from_first_toc_section`
10. Build `final_headings_items`, optional doubted-section resolver (Stage 15b)
11. Optional `persist_to_db` via repositories
12. Return `PipelineResult`

---

## 3. Folder Structure (MESO)

```
AI Notes Creater Model/
├── spec/                      # Authoritative SDD
├── config/default.yaml        # Tunables (MESO Rule 12)
├── src/
│   ├── shared/                # config.py, models.py
│   ├── modules/
│   │   ├── pipeline/          # runner.py (shell), context.py, stages.py, stage_15b.py
│   │   ├── ingestion/
│   │   ├── structure/
│   │   │   └── final_structuring/  # Stage 15b resolver
│   │   ├── generation/        # RewriteEngine, model_router
│   │   ├── export/
│   │   ├── interaction/
│   │   ├── storage/
│   │   └── debug/
│   └── utils/
├── tests/
└── scripts/
```

---

## 4. Pipeline Plugin Flow (Stage 4)

`runner.py` executes `STAGES` in order; each stage mutates `PipelineContext`:

```
extract → layout → noise → candidates → gate → continuity → fragments
→ toc_clean → deterministic_toc → doubted_sections → stage_15b → finalize
```

No business logic in the runner shell — only persistence hook after stages complete.

---

## 5. Design Decisions

| ADR | Decision | Rationale |
|-----|----------|-----------|
| ADR-001 | Deterministic core pipeline | Reproducible structure extraction without LLM dependency |
| ADR-002 | `book_pipeline` re-export | Stable import path for scripts and tests |
| ADR-003 | `shared/models.py` canonical | Single runtime model module; `domain/` is compat shim |
| ADR-004 | SQLite persistence | Local knowledge store for books, topics, TOC graph |
| ADR-005 | Stage JSON logging | Whitelisted artifacts under `logs/run_<timestamp>/` |
| ADR-006 | MESO module layout | `src/modules/*` mirrors `/spec/modules/*`; old paths are shims |
| ADR-007 | Config in `/config` | `default.yaml` + env overlay via `shared/config.py` |
| ADR-008 | Plugin pipeline shell | `stages.py` + `PipelineContext`; runner has no business rules |

---

## 6. Import Policy

| Preferred (canonical) | Legacy (compat shim) |
|-----------------------|----------------------|
| `from src.modules.pipeline import run_pipeline` | `from src.core.pipeline import run_pipeline` |
| `from src.shared.models import NormalizedLine` | `from src.core.models import …` |
| `from src.shared.config import OUTPUT_FOLDER` | `from src.config import …` |
| `from src.modules.ingestion.pdf_extractor import extract_pdf` | `from src.ingestion.pdf_extractor import …` |

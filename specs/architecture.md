# Architecture — InsightEngine

> **Role:** System layers, repo layout, ADRs. Pipeline/web/storage detail in linked module specs.  
> **Authority:** Structural changes MUST update this file BEFORE code (MESO Rule 6).

---

## 1. System Overview

InsightEngine transforms PDF documents into structured AI-generated research notes and summaries. The system has **three entry points** sharing one engine:

```mermaid
flowchart TB
    subgraph entry["Entry Points"]
        CLI["CLI: python main.py"]
        WEB["Web: uvicorn api.main:app"]
        SCRIPTS["Scripts: run_full_openai_pipeline.py"]
    end

    subgraph thin["Thin Layers"]
        API["backend/api/ — FastAPI routes"]
        SVC["backend/services/ — Chat, ingestion, export policy"]
        FE["frontend/ — React SPA"]
    end

    subgraph engine["Core Engine (backend/src/modules/)"]
        PIPE["pipeline/ — Stage orchestrator"]
        ING["ingestion/ — PDF extract, OCR"]
        STR["structure/ — Heading detection, TOC"]
        GEN["generation/ — Rewrite, Q&A"]
        RAG["rag/ — FAISS retrieval"]
        EXP["export/ — Word .docx"]
        INT["interaction/ — CLI loop, intent parser"]
        QLT["quality/ — Post-export audit"]
    end

    subgraph data["Data Layer"]
        KB["KnowledgeStore — books, TOC, fragments, RAG"]
        PLAT["PlatformStore — users, chats, exports"]
        FS["File System — PDFs, logs, docx, FAISS indexes"]
    end

    CLI --> INT
    WEB --> FE --> API --> SVC
    SCRIPTS --> PIPE
    SVC --> INT & GEN & EXP & PIPE & ING
    INT --> GEN & EXP & PIPE
    PIPE --> ING & STR
    GEN --> RAG
    GEN --> QLT
    EXP --> QLT
    SVC --> PLAT & KB
    PIPE --> KB & FS
```

---

## 2. Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Presentation                                                           │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐ │
│  │ React SPA (frontend)│  │ CLI (CommandLoop)   │  │ Debug trace     │ │
│  └──────────┬──────────┘  └──────────┬──────────┘  └────────┬────────┘ │
├─────────────┼────────────────────────┼───────────────────────┼──────────┤
│  Web API    │                        │                       │          │
│  ┌──────────▼──────────┐             │                       │          │
│  │ FastAPI routes      │             │                       │          │
│  │ auth, books, chat,  │             │                       │          │
│  │ exports             │             │                       │          │
│  └──────────┬──────────┘             │                       │          │
├─────────────┼────────────────────────┼───────────────────────┼──────────┤
│  Services   │                        │                       │          │
│  ┌──────────▼────────────────────────▼───────────────────────▼────────┐ │
│  │ IngestionService │ ChatService │ export_policy │ upload_jobs      │ │
│  └──────────┬─────────────────────────────────────────────────────────┘ │
├─────────────┼───────────────────────────────────────────────────────────┤
│  Shared     │                                                           │
│  ┌──────────▼──────────┐  ┌─────────────────────────────────────────┐ │
│  │ shared/models.py    │  │ shared/config.py + config/default.yaml    │ │
│  └─────────────────────┘  └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│  Modules (mirror /spec/modules/)                                        │
│  ingestion │ structure │ pipeline │ generation │ rag │ export │ quality │
│  interaction │ debug                                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Repository Layout

```
InsightEngine/
├── backend/                     # All Python: engine + API + CLI + tests
│   ├── api/                     # FastAPI routes, schemas, main.py
│   ├── auth/                    # OAuth, JWT, dependencies
│   ├── services/                # Chat, ingestion, export policy, upload jobs
│   ├── storage/                 # Platform repositories (users, chats)
│   ├── middleware/              # Rate limiting
│   ├── src/                     # Core engine
│   │   ├── shared/              # config.py, models.py, errors.py
│   │   ├── modules/             # Feature modules (mirror specs/modules/)
│   │   ├── utils/               # pdf_reader, ocr_reader
│   │   ├── config.py            # Shim → shared.config
│   │   └── book_pipeline/       # Stable run_pipeline re-export
│   ├── tests/                   # unit/ + integration/
│   ├── scripts/                 # Ad-hoc pipeline utilities
│   ├── config/                  # default.yaml
│   ├── main.py                  # CLI entry
│   └── requirements.txt
├── frontend/                    # React + Vite SPA
│   ├── auth/                    # API client, AuthProvider, login pages
│   └── src/                     # App.tsx, components, styles
├── specs/                       # Authoritative SDD (this folder)
├── ai-agent-workflow/           # Agent plans & strategy (not authoritative SDD)
├── logs/                        # Runtime: pipeline stage JSON (LOGS_FOLDER)
├── output/                      # Runtime: DB, uploads, exports, RAG indexes
├── models/                      # Local GGUF weights (gitignored)
├── pdfs/                        # Input PDFs (gitignored)
├── .env                         # Secrets (gitignored)
├── .env.example                 # Env template
└── docker-compose.yml           # Backend + frontend containers
```

---

## 4. Pipeline (summary)

PDF → `run_pipeline()` → plugin stages → `PipelineResult` → optional `RewriteEngine` → export → optional `run_quality_audit()`.

**Final structuring:** `partition_tree` → `partition_sections` → `group_chapters` → `place_chapters` → `clean_titles` → `refine_titles` → `cloud_hierarchy` → `validate_titles` → `assemble_book` → `rag_snapshot`.  
`enforce_chapter_structure()` runs after title/placement phases and at rewrite load.

**Authoritative detail:**
- [modules/stage-catalog.md](./modules/stage-catalog.md) — semantic names + legacy 15x mapping
- [modules/pipeline-core.md](./modules/pipeline-core.md) — stage order, registry
- [modules/structure-extraction.md](./modules/structure-extraction.md) — structure modules
- [code-reference/index.md](./code-reference/index.md) — full file/symbol reference with rationale

---

## 5. Web Platform (summary)

Frontend → FastAPI routes → services → engine modules. Auth, upload, chat, export.

**Authoritative detail:**
- Requirements (WHAT): [requirements-web-platform.md](./requirements-web-platform.md)
- REST API (HOW): [backend-api.md](./backend-api.md)
- UI (HOW): [frontend.md](./frontend.md)
- Cross-boundary contracts: [ui-backend-integration.md](./ui-backend-integration.md)

---

## 6. Storage (summary)

All paths resolve under **`PROJECT_ROOT`** (repo root; Docker `PROJECT_ROOT=/workspace`, `working_dir=/workspace/backend`).

| Constant | Path | Contents |
|----------|------|----------|
| `KNOWLEDGE_DB_PATH` | `output/knowledge_base.db` | SQLite (knowledge + platform) |
| `UPLOADS_FOLDER` | `output/uploads/{user_id}/` | Uploaded PDFs |
| `EXPORTS_FOLDER` | `output/exports/{user_id}/` | Generated Word files |
| `RAG_INDEX_DIR` | `output/rag_index/{book_id}/` | FAISS + chunk meta |
| `LOGS_FOLDER` | `logs/run_{timestamp}/` | Stage JSON (`s01`–`s16`) |

**Do not use** `backend/logs/` or `backend/output/` — legacy cwd artifacts; gitignored.

**Authoritative detail:** [data-models.md](./data-models.md) §6 · [modules/parameters-config.md](./modules/parameters-config.md) §2 · [modules/storage.md](./modules/storage.md)

---

## 7. Design Decisions (ADRs)

| ADR | Decision | Rationale |
|-----|----------|-----------|
| ADR-001 | Deterministic core pipeline | Reproducible structure extraction without LLM dependency |
| ADR-002 | `book_pipeline` re-export | Stable import path for scripts and tests |
| ADR-003 | `shared/models.py` canonical | Single runtime model module |
| ADR-004 | SQLite persistence | Local knowledge store; single file for knowledge + platform |
| ADR-005 | Stage JSON logging | Canonical artifacts `s01`–`s16` under `{LOGS_FOLDER}/run_<timestamp>/` |
| ADR-014 | PROJECT_ROOT runtime paths | `logs/` + `output/` at repo root; config constants not cwd-relative |
| ADR-015 | `stage_registry.py` | Single map of log keys → filenames; legacy read fallback |
| ADR-006 | MESO module layout | `src/modules/*` mirrors `/spec/modules/*` |
| ADR-007 | Config in `/config` | `default.yaml` + env overlay via `shared/config.py` |
| ADR-008 | Plugin pipeline shell | `stages.py` + `PipelineContext`; runner has no business rules |
| ADR-009 | Thin web layers | `api/` + `services/` wrap engine; no duplicate business logic |
| ADR-010 | Shared engine CLI + Web | `main.py` and FastAPI both use `src/modules/` |
| ADR-011 | Deterministic intent routing | `CommandParser` keyword-based; no LLM for classification |
| ADR-012 | In-memory upload jobs | Simple for dev; production needs Redis/DB (backlog) |
| ADR-016 | `enforce_chapter_structure` after 15j | 15j OpenAI regroup collapsed syllabus books to 1 chapter; statute prose leaked to export |
| ADR-017 | `specs/code-reference/` symbol docs | Every public file/function documented with purpose + why (rule 13) |
| ADR-018 | Env-driven CORS (`AuthSettings.cors_origins`) | Hardcoded localhost blocked prod; origins now from `FRONTEND_URL` + `CORS_EXTRA_ORIGINS` |
| ADR-019 | Guest mode with isolated session JWT | Let users try the app without OAuth; `ALLOW_GUEST` mints a per-session persisted guest + token |
| ADR-020 | Rewrite disk cache + 15j names-pass skip gate | Cut LLM cost on re-runs / clean docs; bounded retries (`OPENAI_MAX_RETRIES`) for transient errors |
| ADR-021 | Multi-stage prod images (nginx + non-root backend) | Dev compose = hot reload; prod compose = nginx static + `/api` proxy, named volumes, healthchecks (see [deployment.md](./deployment.md)) |

---

## 8. Import Policy

| Preferred (canonical) | Legacy (removed 2026-06-01) |
|-----------------------|----------------------------|
| `from src.modules.pipeline import run_pipeline` | `from src.core.pipeline import run_pipeline` |
| `from src.shared.models import NormalizedLine` | `from src.core.models import …` |
| `from src.shared.config import OUTPUT_FOLDER, LOGS_FOLDER` | `from src.config import …` (shim still works) |
| `from src.modules.pipeline.stage_registry import resolve_existing_artifact` | Hardcoded `15d_ultimate_sections.json` paths |
| `from src.modules.ingestion.pdf_extractor import extract_pdf` | `from src.ingestion.pdf_extractor import …` |

**Web layer imports:**

```python
from auth.dependencies import get_current_user
from services.chat_service import ChatService
from storage.user_repository import ConversationRepository
```

---

## 9. Technology Stack

| Layer | Technology |
|-------|------------|
| Backend API | FastAPI, Uvicorn, Pydantic |
| Auth | PyJWT, OAuth 2.0 (Google, Apple, Facebook) |
| Engine | Python 3.10+, PyMuPDF, Tesseract (optional) |
| LLM | OpenAI, Gemini, Ollama, llama.cpp (configurable) |
| RAG | FAISS, sentence-transformers (MiniLM) |
| Export | python-docx, Pandoc (optional) |
| Database | SQLite |
| Frontend | React 18, TypeScript, Vite 5 |
| Styling | Plain CSS (dark theme) |
| Deploy | Docker Compose (dev hot-reload + prod nginx/uvicorn); see [deployment.md](./deployment.md) |

---

## 10. Related Specs

| Topic | Spec |
|-------|------|
| REST API details | [backend-api.md](./backend-api.md) |
| Frontend details | [frontend.md](./frontend.md) |
| UI↔Backend contracts | [ui-backend-integration.md](./ui-backend-integration.md) |
| Pipeline stages | [modules/pipeline-core.md](./modules/pipeline-core.md) |
| File/symbol reference | [code-reference/index.md](./code-reference/index.md) |
| Data models | [data-models.md](./data-models.md) |
| Tests | [testing.md](./testing.md) |
| Deployment (Docker/env/storage) | [deployment.md](./deployment.md) |
| How to modify | [future-modifications.md](./future-modifications.md) |

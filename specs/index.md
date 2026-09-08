# SPEC INDEX — InsightEngine

> **This folder is the authoritative SDD.** Start every task here (MESO Rule 10).

---

## Document Hierarchy (single source of truth)

Each topic has **one authoritative spec**. Other files link to it — they do not repeat it.

| Layer | Role | Authoritative files |
|-------|------|-------------------|
| **Navigation** | Where to go | `index.md` (this file) |
| **Summary** | One-page intro | `overview.md` |
| **Architecture** | Layers, ADRs, repo layout | `architecture.md` |
| **Requirements** | WHAT (requirement IDs) | `requirements-web-platform.md`, `requirements-ocr-stage.md` |
| **Engine modules** | HOW per module | `modules/*.md` |
| **Web API** | REST endpoints, services | `backend-api.md` |
| **Frontend** | UI components, state | `frontend.md` |
| **Integration** | UI↔API contracts only | `ui-backend-integration.md` |
| **Data** | All schemas & entities | `data-models.md` |
| **Config** | All env vars & YAML | `modules/parameters-config.md` |
| **API index** | Links to modules | `api.md` |
| **Tests** | All test cases | `testing.md` |
| **Changes** | Audit trail | `change-log.md` |
| **Code reference** | Every file/function + why | `code-reference/*.md` |

**Rule:** When updating a topic, edit the authoritative file only. Update links elsewhere if paths change.

---

## 1. Root Spec Files

| File | Purpose |
|------|---------|
| [overview.md](./overview.md) | Executive summary |
| [architecture.md](./architecture.md) | System layers, ADRs, repo layout |
| [api.md](./api.md) | Index → module specs + backend-api |
| [backend-api.md](./backend-api.md) | REST API (authoritative) |
| [frontend.md](./frontend.md) | React UI (authoritative) |
| [ui-backend-integration.md](./ui-backend-integration.md) | UI↔API contracts (authoritative) |
| [data-models.md](./data-models.md) | Schemas & entities (authoritative) |
| [testing.md](./testing.md) | Test catalog (authoritative) |
| [future-modifications.md](./future-modifications.md) | How to extend safely |
| [deployment.md](./deployment.md) | Docker dev/prod, env profiles, storage strategy |
| [requirements-web-platform.md](./requirements-web-platform.md) | Web requirement IDs (WHAT) |
| [change-log.md](./change-log.md) | Append-only history |
| [code-reference/index.md](./code-reference/index.md) | Exhaustive file/symbol inventory |
| [unused-tracking.md](./unused-tracking.md) | Dead code registry |

---

## 2. Module Specs (Engine — authoritative per module)

| # | Spec | Code |
|---|------|------|
| 01 | [cli-interaction.md](./modules/cli-interaction.md) | `backend/src/modules/interaction/` |
| 02 | [pipeline-core.md](./modules/pipeline-core.md) | `backend/src/modules/pipeline/` |
| 02b | [stage-catalog.md](./modules/stage-catalog.md) | Semantic stage names + structure phases |
| 03 | [ingestion.md](./modules/ingestion.md) | `backend/src/modules/ingestion/` |
| 04 | [structure-extraction.md](./modules/structure-extraction.md) | `backend/src/modules/structure/` |
| 05 | [toc-persistence.md](./modules/toc-persistence.md) | `structure/toc_*`, `storage/` |
| 06 | [logging-debug.md](./modules/logging-debug.md) | `logging/`, `debug/` |
| 07 | [storage.md](./modules/storage.md) | `storage/` (repos — schemas in data-models) |
| 08 | [llm-generation.md](./modules/llm-generation.md) | `generation/` |
| 09 | [export.md](./modules/export.md) | `export/` + `export_policy` |
| 10 | [parameters-config.md](./modules/parameters-config.md) | `config/`, `shared/config.py` |
| 11 | [rag-retrieval.md](./modules/rag-retrieval.md) | `rag/` |
| 12 | [quality.md](./modules/quality.md) | `quality/` |
| 13 | [pipeline-signal-sections.md](./modules/pipeline-signal-sections.md) | `structure/signal_sections/`, `generation/signal_rewrite/`, `export/signal_export/` (parallel V2, opt-in) |

Supplementary: [requirements-ocr-stage.md](./requirements-ocr-stage.md)

---

## 3. Traceability Matrix

| Spec | Code |
|------|------|
| `data-models.md` | `shared/models.py`, `storage/schema.py`, `storage/user_repository.py` |
| `modules/pipeline-core.md` | `pipeline/runner.py`, `stages.py`, `stage_registry.py` |
| `modules/pipeline-signal-sections.md` | `structure/signal_sections/*`, `generation/signal_rewrite/*`, `export/signal_export/*`, `scripts/pipeline_signal_sections.py` |
| `modules/cli-interaction.md` | `interaction/command_parser.py`, handlers |
| `backend-api.md` | `api/`, `services/`, `auth/`, `storage/` |
| `frontend.md` | `frontend/src/`, `frontend/auth/` |
| `modules/parameters-config.md` | `config/default.yaml`, `shared/config.py` |
| `testing.md` | `backend/tests/` |
| `modules/quality.md` | `quality/` |

---

## 4. Workflow (MESO Rule 10)

1. Read this `index.md` → find authoritative spec for your topic
2. For file/function detail → [code-reference/index.md](./code-reference/index.md)
3. Update authoritative spec FIRST (or code-reference if adding symbols)
4. Implement code → tests → `change-log.md`

Guide: [future-modifications.md](./future-modifications.md)

---

## 5. Quick Navigation

| Task | Read |
|------|------|
| Understand system | [architecture.md](./architecture.md) |
| Web requirement IDs | [requirements-web-platform.md](./requirements-web-platform.md) |
| Add API endpoint | [backend-api.md](./backend-api.md) §11 |
| Change UI | [frontend.md](./frontend.md) §11 |
| UI↔API contract | [ui-backend-integration.md](./ui-backend-integration.md) |
| Pipeline stage / log artifacts | [modules/pipeline-core.md](./modules/pipeline-core.md) · `stage_registry.py` |
| Runtime paths (logs, output) | [modules/parameters-config.md](./modules/parameters-config.md) §2 |
| Local ingestion roadmap | [change-plan-local-ingestion.md](../ai-agent-workflow/change-plan-local-ingestion.md) |
| TOC / sections / RAG strategy (agent workflow) | [ingestion-toc-rag-strategy.md](../ai-agent-workflow/ingestion-toc-rag-strategy.md) |
| Export policy | [modules/export.md](./modules/export.md) §3 |
| Config / env | [modules/parameters-config.md](./modules/parameters-config.md) |
| Tests | [testing.md](./testing.md) |
| Notes quality audit | [modules/quality.md](./modules/quality.md) · [code-reference/quality.md](./code-reference/quality.md) |
| File/function reference | [code-reference/index.md](./code-reference/index.md) |

---

## 6. Quick Start

```bash
cd backend && pip install -r requirements.txt && uvicorn api.main:app --reload --port 8000
cd frontend && npm install && npm run dev   # http://localhost:5173
cd backend && pytest tests/unit
```

Set `AUTH_ENABLED=false` in `.env` for local dev without OAuth.

---

## 7. Agent Workflow Docs

Analysis and execution notes live in [`../ai-agent-workflow/`](../ai-agent-workflow/) (not part of authoritative SDD):

| File | Purpose |
|------|---------|
| [SDD.md](../ai-agent-workflow/SDD.md) | Pointer to this index |
| [requirements.md](../ai-agent-workflow/requirements.md) | MESO requirements summary |
| [tasks.md](../ai-agent-workflow/tasks.md) | Stage checklist |
| [ingestion-toc-rag-strategy.md](../ai-agent-workflow/ingestion-toc-rag-strategy.md) | TOC / sections / RAG roadmap analysis |
| [change-plan-local-ingestion.md](../ai-agent-workflow/change-plan-local-ingestion.md) | Local upload plan — Phase 0/5 paths & registry **done**; FLAN/RAG pending |

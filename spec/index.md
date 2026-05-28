# SPEC INDEX — AI Notes Creator Model

> **MESO Rule 1:** This spec is the single source of truth. Code must NEVER lead the spec.
> **MESO Rule 10:** Every task begins here.

---

## 1. Root Spec Files

| File | Purpose | Status |
|------|---------|--------|
| [SDD.md](./SDD.md) | Final SDD declaration + document map | **ACTIVE** |
| [overview.md](./overview.md) | Purpose, goals, end-to-end flow | **ACTIVE** |
| [architecture.md](./architecture.md) | Components, folder structure, data flow | **ACTIVE** |
| [api.md](./api.md) | Public contracts (functions, CLI, handlers) | **ACTIVE** |
| [data-models.md](./data-models.md) | Entities, schema, naming | **ACTIVE** |
| [change-log.md](./change-log.md) | What / Why / Impact (append-only) | **ACTIVE** |
| [unused-tracking.md](./unused-tracking.md) | Dead code registry | **ACTIVE** |

---

## 2. Module Specs

| # | Module Spec | Code Package | Legacy doc |
|---|-------------|--------------|------------|
| 01 | [cli-interaction.md](./modules/cli-interaction.md) | `src/modules/interaction/` | `doc/spec/01-entry-cli-interaction.md` |
| 02 | [pipeline-core.md](./modules/pipeline-core.md) | `src/modules/pipeline/` | `doc/spec/02-pipeline-core-chain.md` |
| 03 | [ingestion.md](./modules/ingestion.md) | `src/modules/ingestion/` | `doc/spec/03-ingestion-layer.md` |
| 04 | [structure-extraction.md](./modules/structure-extraction.md) | `src/modules/structure/` | `doc/spec/04-structure-extraction-chain.md` |
| 05 | [toc-persistence.md](./modules/toc-persistence.md) | `src/modules/structure/toc_*`, `src/modules/storage/` | `doc/spec/05-deterministic-toc-persistence.md` |
| 06 | [logging-debug.md](./modules/logging-debug.md) | `src/modules/structure/logging/`, `src/modules/debug/` | `doc/spec/06-logging-debug-visualization.md` |
| 07 | [storage.md](./modules/storage.md) | `src/modules/storage/` | `doc/spec/07-storage-repositories.md` |
| 08 | [llm-generation.md](./modules/llm-generation.md) | `src/modules/generation/`, `src/modules/pipeline/llm_chat_client.py` | `doc/spec/08-llm-tools-optional.md` |
| 09 | [export.md](./modules/export.md) | `src/modules/export/` | — |
| 10 | [parameters-config.md](./modules/parameters-config.md) | `config/default.yaml`, `src/shared/config.py` | — |

---

## 3. Spec ⇄ Code Traceability Matrix

| Spec | Authoritative code |
|------|-------------------|
| `data-models.md` | `src/shared/models.py`, `src/storage/schema.py` |
| `api.md` §1 | `src/modules/pipeline/runner.py::run_pipeline` |
| `api.md` §2 | `src/book_pipeline/__init__.py` (re-export) |
| `api.md` §3 | `src/modules/interaction/command_loop.py`, `command_parser.py` |
| `parameters-config.md` | `config/default.yaml`, `src/shared/config.py` |
| `storage.md` | `src/modules/storage/knowledge_store.py`, `*_repository.py` |
| `pipeline-core.md` | `src/modules/pipeline/runner.py` stage order |
| `structure-extraction.md` | `src/modules/structure/*.py` (noise → fragments) |

---

## 4. Execution Flow (MESO Rule 10)

1. Read this `index.md`
2. Read relevant module spec(s)
3. **Update spec FIRST** → code → tests → `change-log.md`
4. Validate Spec ⇄ Code ⇄ Tests alignment

---

## 5. Quick Links

- Legacy call-chain docs: [`../doc/spec/README.md`](../doc/spec/README.md) (being superseded by `/spec`)
- Source: [`../src/`](../src/)
- Tests: [`../tests/`](../tests/)
- Config: [`../config/`](../config/) | [`../src/shared/config.py`](../src/shared/config.py)
- Workflow: [`../ai-agent-workflow/`](../ai-agent-workflow/)

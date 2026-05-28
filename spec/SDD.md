# Software Design Document (SDD)

> **Status:** ACTIVE — baseline established 2026-05-27 via MESO bootstrap  
> **Navigation:** [index.md](./index.md)

---

## 1. Declaration

The **`/spec` directory is the authoritative SDD** for the AI Notes Creator Model project.

Legacy call-chain documentation in `doc/spec/` is retained for reference but **superseded by `/spec`** for all future changes (MESO Rule 1).

---

## 2. SDD Document Map

| SDD Section | Spec file(s) | Content |
|-------------|--------------|---------|
| Executive summary | [overview.md](./overview.md) | Purpose, entry points, package map |
| System architecture | [architecture.md](./architecture.md) | Layers, pipeline stages, folder structure |
| API & contracts | [api.md](./api.md) | `run_pipeline`, CLI, handlers, LLM client |
| Data model | [data-models.md](./data-models.md) | Pipeline entities, SQLite schema |
| Parameters | [modules/parameters-config.md](./modules/parameters-config.md) | Env vars, chunking, LLM provider keys |
| Pipeline orchestration | [modules/pipeline-core.md](./modules/pipeline-core.md) | Stage order, logging, persistence hooks |
| Ingestion | [modules/ingestion.md](./modules/ingestion.md) | PDF extract, normalize, layout |
| Structure extraction | [modules/structure-extraction.md](./modules/structure-extraction.md) | Noise, candidates, gate, continuity, fragments |
| TOC & persistence | [modules/toc-persistence.md](./modules/toc-persistence.md) | Deterministic TOC, metadata, DB save |
| Logging & debug | [modules/logging-debug.md](./modules/logging-debug.md) | PipelineLogger, trace runner, visualizer |
| Storage | [modules/storage.md](./modules/storage.md) | KnowledgeStore, repositories |
| LLM & generation | [modules/llm-generation.md](./modules/llm-generation.md) | Doubted resolver, rewrite stub, model router |
| Export | [modules/export.md](./modules/export.md) | Word export, OutputManager |
| CLI | [modules/cli-interaction.md](./modules/cli-interaction.md) | CommandLoop, intent routing |
| Change history | [change-log.md](./change-log.md) | Append-only audit trail |
| Dead code | [unused-tracking.md](./unused-tracking.md) | Stubs, duplicates, legacy references |

---

## 3. Implementation Traceability

| Layer | Code root |
|-------|-----------|
| Orchestration | `src/modules/pipeline/runner.py` |
| Shared types | `src/shared/models.py` |
| Configuration | `config/default.yaml`, `src/shared/config.py` |
| Modules | `src/modules/*` (mirrors module specs 01–10) |
| Tests | `tests/` |

---

## 4. Known Gaps (approved backlog)

- `AskHandler` — single-question Q&A not wired from CLI
- `doc/spec/RESTRUCTURE-PLAN.md` — further stage file splits optional (core plugin shell done)

---

## 5. Revision Policy

1. Edit the relevant spec file first (MESO Rule 6).
2. Implement code + tests.
3. Append [change-log.md](./change-log.md).
4. Update [unused-tracking.md](./unused-tracking.md) if dead code found (MESO Rule 7).

# API Contracts — Index

> **Role:** Navigation index only. Detailed contracts live in module specs and [backend-api.md](./backend-api.md).  
> **MESO Rule 8:** Names listed here must exist in code with identical signatures.

---

## Web Platform (REST + SSE)

**Authoritative:** [backend-api.md](./backend-api.md)

Covers: endpoints, Pydantic schemas, services, auth, SSE, platform storage.

---

## Engine Modules

| Area | Authoritative spec | Key entry point |
|------|-------------------|-----------------|
| Pipeline | [modules/pipeline-core.md](./modules/pipeline-core.md) | `run_pipeline()` |
| Ingestion | [modules/ingestion.md](./modules/ingestion.md) | `extract_pdf()` |
| Structure | [modules/structure-extraction.md](./modules/structure-extraction.md) | `mark_noise()`, `build_fragments()`, … |
| TOC & persist | [modules/toc-persistence.md](./modules/toc-persistence.md) | `detect_deterministic_toc()`, `save_full_toc()` |
| CLI & intents | [modules/cli-interaction.md](./modules/cli-interaction.md) | `CommandParser`, handlers |
| LLM & generation | [modules/llm-generation.md](./modules/llm-generation.md) | `RewriteEngine`, `BookQaEngine` |
| RAG | [modules/rag-retrieval.md](./modules/rag-retrieval.md) | `RagService` |
| Export | [modules/export.md](./modules/export.md) | `WordExporter`, `export_policy` |
| Storage | [modules/storage.md](./modules/storage.md) | `KnowledgeStore`, repositories |
| Logging & debug | [modules/logging-debug.md](./modules/logging-debug.md) | `PipelineLogger`, `run_toc_trace` |
| Config | [modules/parameters-config.md](./modules/parameters-config.md) | env vars, `default.yaml` |

---

## Data Types

**Authoritative:** [data-models.md](./data-models.md)

Pipeline entities (`NormalizedLine`, `PipelineResult`, …) and SQLite schemas.

---

## Cross-Boundary Contracts (UI ↔ API)

**Authoritative:** [ui-backend-integration.md](./ui-backend-integration.md)

Auth, upload polling, SSE events, export download URLs.

# Overview — InsightEngine

> **Role:** One-page executive summary. Details live in linked specs below.

---

## Purpose

Transform **PDF documents** into structured AI-generated research notes and summaries via:

1. Deterministic pipeline (ingest → structure → TOC → final structuring)
2. Optional LLM overlays (rewrite, Q&A with RAG)
3. Word export with smart delivery policy
4. Web chat UI with OAuth **or guest mode** and conversation history
5. Post-export **notes quality audit** (heading AC, line-by-line content)

Subject-agnostic by design (law, medicine, maths, etc.). Deployable via Docker
(dev + prod). LLM cost is reduced via a rewrite disk cache and a stage-15j
names-pass skip gate, with bounded retries for transient API errors.

**Full symbol reference:** [code-reference/index.md](./code-reference/index.md)

---

## Entry Points

| Entry | Command |
|-------|---------|
| CLI | `cd backend && python main.py` |
| Web API | `cd backend && uvicorn api.main:app --port 8000` |
| Web UI | `cd frontend && npm run dev` |
| Docker (dev) | `docker compose up --build` |
| Docker (prod) | `docker compose -f docker-compose.prod.yml up -d --build` |

Quick start commands: [index.md](./index.md) §6

---

## Capabilities

| Capability | CLI | Web | Spec |
|------------|-----|-----|------|
| PDF ingestion | ✓ | ✓ | [modules/ingestion.md](./modules/ingestion.md) |
| Full book rewrite | ✓ | ✓ | [modules/llm-generation.md](./modules/llm-generation.md) |
| Q&A with RAG | ✓ | ✓ | [modules/rag-retrieval.md](./modules/rag-retrieval.md) |
| Word export | ✓ | ✓ | [modules/export.md](./modules/export.md) |
| OAuth / guest + chat history | — | ✓ | [requirements-web-platform.md](./requirements-web-platform.md) |
| Docker deployment (dev/prod) | — | ✓ | [deployment.md](./deployment.md) |
| Pipeline debug logs | ✓ | ✓ | [modules/logging-debug.md](./modules/logging-debug.md) |
| Notes quality audit | ✓ (scripts) | — | [modules/quality.md](./modules/quality.md) |
| Batch regression (4 PDFs) | ✓ | — | `scripts/run_batch_pipeline.py` · [code-reference/services-scripts.md](./code-reference/services-scripts.md) |

---

## Runtime Data (gitignored)

| Path | Purpose |
|------|---------|
| `logs/run_*/` | Pipeline stage JSON (`s01`–`s16`) |
| `output/` | SQLite DB, uploads, exports, RAG indexes |

Config: [modules/parameters-config.md](./modules/parameters-config.md) §2. Do not use `backend/logs/` or `backend/output/`.

---

## Where to Read Next

| Topic | Document |
|-------|----------|
| System architecture & layers | [architecture.md](./architecture.md) |
| Web requirements (IDs) | [requirements-web-platform.md](./requirements-web-platform.md) |
| REST API | [backend-api.md](./backend-api.md) |
| Frontend | [frontend.md](./frontend.md) |
| Deployment (Docker/env/storage) | [deployment.md](./deployment.md) |
| All specs index | [index.md](./index.md) |

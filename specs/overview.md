# Overview — AI Notes Creator Model

> **Role:** One-page executive summary. Details live in linked specs below.

---

## Purpose

Transform legal/academic **PDF books** into structured AI-generated notes via:

1. Deterministic pipeline (ingest → structure → TOC → final structuring)
2. Optional LLM overlays (rewrite, Q&A with RAG)
3. Word export with smart delivery policy
4. Web chat UI with OAuth and conversation history

---

## Entry Points

| Entry | Command |
|-------|---------|
| CLI | `cd backend && python main.py` |
| Web API | `cd backend && uvicorn api.main:app --port 8000` |
| Web UI | `cd frontend && npm run dev` |
| Docker | `docker compose up --build` |

Quick start commands: [index.md](./index.md) §6

---

## Capabilities

| Capability | CLI | Web | Spec |
|------------|-----|-----|------|
| PDF ingestion | ✓ | ✓ | [modules/ingestion.md](./modules/ingestion.md) |
| Full book rewrite | ✓ | ✓ | [modules/llm-generation.md](./modules/llm-generation.md) |
| Q&A with RAG | ✓ | ✓ | [modules/rag-retrieval.md](./modules/rag-retrieval.md) |
| Word export | ✓ | ✓ | [modules/export.md](./modules/export.md) |
| OAuth + chat history | — | ✓ | [requirements-web-platform.md](./requirements-web-platform.md) |
| Pipeline debug logs | ✓ | ✓ | [modules/logging-debug.md](./modules/logging-debug.md) |

---

## Where to Read Next

| Topic | Document |
|-------|----------|
| System architecture & layers | [architecture.md](./architecture.md) |
| Web requirements (IDs) | [requirements-web-platform.md](./requirements-web-platform.md) |
| REST API | [backend-api.md](./backend-api.md) |
| Frontend | [frontend.md](./frontend.md) |
| All specs index | [index.md](./index.md) |

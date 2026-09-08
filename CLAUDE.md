# CLAUDE.md — AI Notes Creator Model

> Authoritative onboarding doc for Claude Code (and any AI agent).
> For Cursor-specific rules see `.cursor/rules/`. This file mirrors the same conventions.

---

## Project Overview

**AI Notes Creator Model** converts PDF textbooks into structured, LLM-rewritten study notes exported as Word (`.docx`) documents.

- **Backend** — Python/FastAPI pipeline (`backend/`)
- **Frontend** — React/Vite web UI (`frontend/`)
- **Specs** — Single-source-of-truth SDD (`specs/`)
- **Agent workflow** — Planning artifacts (`ai-agent-workflow/`)

---

## Quick Start

```bash
# Backend (FastAPI)
cd backend && pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Frontend (React/Vite)
cd frontend && npm install && npm run dev   # http://localhost:5173

# Unit tests
cd backend && pytest tests/unit

# CLI pipeline (no web server needed)
python backend/scripts/run_full_openai_pipeline.py <path/to/book.pdf>

# Signal-sections V2 pipeline (opt-in, parallel)
python backend/scripts/pipeline_signal_sections.py <path/to/book.pdf>
```

Set `AUTH_ENABLED=false` in `.env` for local dev without OAuth.

---

## Repo Layout

```
backend/
  src/modules/
    ingestion/        # PDF parsing, OCR, layout enrichment
    structure/        # TOC extraction, section hierarchy, final structuring
    generation/       # LLM rewrite (full pipeline + signal_rewrite V2)
    export/           # DOCX export, themes, markdown renderer
    quality/          # Post-pipeline audit
    pipeline/         # Stage runner + registry
    rag/              # Vector + lexical retrieval
    storage/          # Repositories (SQLite)
    config/           # default.yaml + shared/config.py
  api/                # FastAPI routes, services, auth
  scripts/            # CLI entry points
  tests/unit/         # pytest unit tests

frontend/
  src/                # React components, state, auth

specs/                # Authoritative SDD (read before editing)
ai-agent-workflow/    # Planning docs, task lists, change plans
.cursor/rules/        # Cursor agent behavior rules (≈ this file, more granular)
```

---

## Model, Cost & Context

- Default model: **opusplan** (Opus in Plan mode → Sonnet for execution). Set in `.claude/settings.json`.
- Escalate to Opus (`/model opus`) only for: subtle bugs, architecture decisions, or a problem Sonnet already failed on.
- Drop to Haiku (`/model haiku`) for trivial edits: renames, formatting, boilerplate.
- Context hygiene: run `/context` to check fill. At ~50% consider `/compact`; at ~80% compact or `/clear` before a new task.
- For verbose read-heavy exploration ("how does X work?") use the **explorer** subagent — keeps large reads out of the main thread.
- Custom command: `/optimize` — audits context and recommends the cheapest next action.

---

## Spec-First Workflow (MESO Rule 10)

1. Read `specs/index.md` → find the authoritative spec for your topic.
2. For file/function detail → `specs/code-reference/index.md`.
3. **Update the authoritative spec first**, then implement code, then tests, then `specs/change-log.md`.

Do **not** edit code without reading the relevant spec first.

---

## Environment

Copy `.env.example` → `.env` and fill secrets. Key variables:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `OPENAI` or `OPENROUTER` |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | LLM credentials |
| `AUTH_ENABLED` | `false` for local dev |
| `INGESTION_PROFILE` | `fast_local` \| `quality_cloud` \| `debug` |
| `EXPORT_DOCX` | `1` to produce Word output |
| `DOCX_THEME` | `color` \| `plain` |
| `NOTES_EXPORT_STYLE` | `book` (prose) \| `study` (bullets) |
| `RAG_ENABLED` | `1` to enable vector retrieval |

Never commit `.env`. The overlay order is: `default.yaml` → system env → `.env`.

---

## Architecture Rules

- Keep concerns separated: routes / services / schemas / persistence / background jobs / UI.
- All new capabilities: define schema first → service boundary → persistence → API/UI → tests → docs.
- No circular dependencies, hidden global state, or hardcoded credentials.
- Structured logging; include request/job/resource IDs; never log secrets.
- Configuration over hardcoding.

---

## Code Style

- Python with type annotations throughout.
- Explicit error handling — no silent swallowing of exceptions.
- Small focused modules and functions.
- No magic constants; use `config/` or env vars.
- Comments only for non-obvious WHY, not what the code does.

---

## Testing

```bash
cd backend && pytest tests/unit          # full unit suite
cd backend && pytest tests/unit/test_X.py  # single file
```

Rules:
- Deterministic tests; mock external services; no live network calls in unit tests.
- Use fixtures for sample data; label synthetic data clearly.
- No secrets required to run tests.

A task is complete only when: feature works + tests pass + errors handled + logs meaningful + docs updated.

---

## Key Module Pointers

| Topic | Spec | Code |
|---|---|---|
| Pipeline stages | `specs/modules/pipeline-core.md` | `backend/src/modules/pipeline/` |
| Structure/TOC | `specs/modules/structure-extraction.md` | `backend/src/modules/structure/` |
| DOCX export | `specs/modules/export.md` | `backend/src/modules/export/` |
| LLM rewrite | `specs/modules/llm-generation.md` | `backend/src/modules/generation/` |
| Ingestion/OCR | `specs/modules/ingestion.md` | `backend/src/modules/ingestion/` |
| Signal pipeline V2 | `specs/modules/pipeline-signal-sections.md` | `backend/src/modules/structure/signal_sections/` |
| Quality audit | `specs/modules/quality.md` | `backend/src/modules/quality/` |
| Config/env vars | `specs/modules/parameters-config.md` | `backend/src/config/`, `shared/config.py` |
| REST API | `specs/backend-api.md` | `backend/src/api/` |
| Frontend | `specs/frontend.md` | `frontend/src/` |

---

## What Not To Do

- Do not fabricate API responses, test results, or benchmark numbers.
- Do not implement unrelated features alongside a requested change.
- Do not refactor beyond the scope of the task.
- Do not bypass failing tests with `--no-verify` or skip markers without explanation.
- Do not commit `.env` or any secrets.
- Do not add backwards-compatibility shims for dead code — delete it.

---

## After Any Meaningful Change

Summarize:
1. Files created / modified
2. Tests run and outcome
3. Known limitations
4. Next recommended step
5. Append a one-line entry to `specs/change-log.md`

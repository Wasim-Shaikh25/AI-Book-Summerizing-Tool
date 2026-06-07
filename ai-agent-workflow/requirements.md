# Requirements — AI Notes Creator Model

> MESO-aligned requirements document. Authoritative design: [`../specs/index.md`](../specs/index.md).  
> Web platform: [`../specs/requirements-web-platform.md`](../specs/requirements-web-platform.md).

---

## Problem Definition

Legal/academic PDF books need automated structure extraction (headings, fragments, TOC) and optional AI-assisted note generation/export — without losing reproducibility or traceability. Users also need a web UI with OAuth login, per-user chat history, and smart Word export.

---

## Scope

**In scope:**

- PDF ingestion with layout metadata and OCR
- Deterministic heading/fragment/TOC pipeline
- SQLite persistence + RAG retrieval
- LLM doubted-section resolver and rewrite
- Word export and CLI interaction
- **Web API** (`backend/`) and **React UI** (`frontend/`)
- OAuth auth (Google, Apple, Facebook)
- Per-user conversations and chat history
- Smart Word export policy (rewrite always, Q&A threshold, explicit request)

**Out of scope (current baseline):**

- Multi-tenant cloud production deploy (Docker scaffold only)
- PostgreSQL (SQLite default)

---

## Functional Requirements

| ID | Requirement |
|----|-------------|
| FR1 | Ingest PDF and produce normalized line stream with layout flags |
| FR2 | Detect heading candidates, apply validity and continuity filters |
| FR3 | Build fragments and clean TOC sections deterministically |
| FR4 | Persist book/TOC graph to SQLite |
| FR5 | Log whitelisted stage JSON for debugging |
| FR6 | Export structured content to Word `.docx` |
| FR7 | Support multiple LLM providers via centralized config |
| FR8 | Resolve doubted sections via optional Stage 15b local LLM |
| FR9 | Web users sign in via Google/Apple/Facebook OAuth |
| FR10 | Web chat with persistent conversation history per user |
| FR11 | Full PDF rewrite always produces Word file in web + CLI |
| FR12 | Q&A in chat; auto Word when answer exceeds char limit or user asks |

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR1 | Deterministic core path must run without LLM |
| NFR2 | All tunables in `config/default.yaml` / `.env` |
| NFR3 | Spec precedes code; changes logged in `spec/change-log.md` |
| NFR4 | No duplicate business logic across modules |
| NFR5 | API rate limiting and upload size caps |

---

## Assumptions

- Input PDFs are text-based or OCR-fallback capable
- Local GGUF models available under `models/` for llama.cpp path
- Pandoc optional; primary export via `python-docx`
- OAuth credentials configured in `.env` for web login

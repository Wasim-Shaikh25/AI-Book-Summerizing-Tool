# Web Platform Requirements — AI Notes Creator

> **Role:** Functional requirements only (WHAT). Implementation detail in linked specs.  
> **Version:** 3.0 — deduplicated 2026-06-07

| Need | Authoritative spec |
|------|------------------|
| Architecture | [architecture.md](./architecture.md) |
| REST API | [backend-api.md](./backend-api.md) |
| Frontend | [frontend.md](./frontend.md) |
| UI↔API contracts | [ui-backend-integration.md](./ui-backend-integration.md) |
| Data schemas | [data-models.md](./data-models.md) §3 |
| Export policy (HOW) | [modules/export.md](./modules/export.md) §3 |
| Config / env | [modules/parameters-config.md](./modules/parameters-config.md) §8 |

---

## 1. Problem Statement

Users need a web platform wrapping the existing CLI engine:

- REST API over pipeline / generation / export modules
- OAuth login (Google, Apple, Facebook)
- ChatGPT-style UI with per-user conversation history
- Smart Word (`.docx`) delivery rules

Project layout: [architecture.md](./architecture.md) §3

---

## 2. Functional Requirements

### 2.1 Authentication (AUTH-*)

| ID | Requirement |
|----|-------------|
| AUTH-01 | Sign in via Google, Apple, or Facebook OAuth 2.0 |
| AUTH-02 | Backend issues signed JWT after OAuth callback |
| AUTH-03 | Chat/book/export endpoints require JWT (except health + OAuth redirect) |
| AUTH-04 | User profile: `user_id`, `email`, `display_name`, `provider`, `provider_user_id`, `avatar_url` |
| AUTH-05 | Frontend stores JWT in `localStorage`; redirects unauthenticated users |
| AUTH-06 | `AUTH_ENABLED=false` enables guest dev mode |
| AUTH-07 | `GET /api/auth/config` returns `{ auth_enabled: bool }` |

Implementation: [backend-api.md](./backend-api.md) §4.2 · Flow: [ui-backend-integration.md](./ui-backend-integration.md) §2

### 2.2 Book Ingestion (ING-*)

| ID | Requirement |
|----|-------------|
| ING-01 | Upload PDF via `POST /api/books/upload` |
| ING-02 | Triggers `extract_pdf` → `run_pipeline` → `save_full_toc` → optional RAG |
| ING-03 | Book linked in `user_books` table |
| ING-04 | Returns `book_id`, title, page count, status |
| ING-05 | Async upload with `job_id`; poll `GET /api/books/upload/{job_id}` |
| ING-06 | Max size `MAX_UPLOAD_MB` (default 100 MB) |
| ING-07 | RAG index skipped by default (`UPLOAD_SKIP_RAG=true`) |

Implementation: [backend-api.md](./backend-api.md) §4.3 · Engine: [modules/ingestion.md](./modules/ingestion.md)

### 2.3 Chat & Conversations (CHAT-*)

| ID | Requirement |
|----|-------------|
| CHAT-01 | Multiple conversations per user, each tied to one book |
| CHAT-02 | Messages: role, content, timestamps, optional `docx_url` |
| CHAT-03 | `GET /api/conversations` — list with title, book, last updated |
| CHAT-04 | `GET /api/conversations/{id}/messages` — full history |
| CHAT-05 | `POST /api/conversations/{id}/messages` — send and receive response |
| CHAT-06 | `POST /api/conversations` — create conversation for a book |
| CHAT-07 | Intent routing via `CommandParser` (deterministic, no LLM) |
| CHAT-08 | UI: loading states, markdown, download links when docx available |
| CHAT-09 | SSE via `POST .../messages/stream` with status events |
| CHAT-10 | Rate limiting per IP (`RATE_LIMIT_REQUESTS`) |

Implementation: [backend-api.md](./backend-api.md) §4.4 · UI: [frontend.md](./frontend.md)

### 2.4 Word Export Policy (EXP-*)

| ID | Requirement | Trigger |
|----|-------------|---------|
| EXP-01 | Full rewrite always produces `.docx` | Automatic |
| EXP-02 | Q&A returns answer in chat by default | Default |
| EXP-03 | Q&A answer > `CHAT_DOCX_CHAR_LIMIT` (4000) → auto `.docx` | Automatic |
| EXP-04 | User asks for Word/docx → generate `.docx` | Explicit request |
| EXP-05 | Download via `GET /api/exports/{id}` — user owns file | — |
| EXP-06 | Message metadata: `docx_available`, `docx_download_url` | — |

Implementation: [modules/export.md](./modules/export.md) §3 · Tests: [testing.md](./testing.md) §5.1

### 2.5 Frontend UI (UI-*)

| ID | Requirement |
|----|-------------|
| UI-01 | Sidebar (conversations) + main chat panel |
| UI-02 | Login with Google / Apple / Facebook |
| UI-03 | PDF upload drag-and-drop or file picker |
| UI-04 | Markdown messages; download button when docx available |
| UI-05 | New chat per book; auto-generated conversation titles |
| UI-06 | Responsive (desktop-first, usable on tablet) |
| UI-07 | Dark theme, DM Sans font |
| UI-08 | Vite proxy `/api` → backend |
| UI-09 | Guest mode when `AUTH_ENABLED=false` |

Implementation: [frontend.md](./frontend.md)

---

## 3. Non-Functional Requirements (NFR-*)

| ID | Requirement |
|----|-------------|
| NFR-01 | Backend: FastAPI, Python 3.10+ |
| NFR-02 | Frontend: React 18 + Vite + TypeScript |
| NFR-03 | CORS for frontend origin |
| NFR-04 | PDFs under `output/uploads/{user_id}/` |
| NFR-05 | Docx under `output/exports/{user_id}/` |
| NFR-06 | JWT expiry configurable (default 7 days) |
| NFR-07 | Secrets in `.env` only |
| NFR-08 | CLI (`main.py`) unchanged |

Config keys: [modules/parameters-config.md](./modules/parameters-config.md) §8

---

## 4. Implementation Phases

### Phase 1 — Foundation (complete)
- [x] Requirements, FastAPI, OAuth, JWT, user storage, chat service, frontend scaffold

### Phase 2 — Polish (in progress)
- [x] SSE streaming, title auto-generation, rate limits, upload size cap
- [ ] Apple Sign In production setup

### Phase 3 — Production
- [x] Docker compose scaffold
- [ ] PostgreSQL option
- [ ] HTTPS, secrets rotation

---

## 5. Acceptance Criteria

1. Google login works (Apple/Facebook with env vars).
2. PDF upload → ingestion → chat enabled.
3. "Rewrite full book" → docx link automatically.
4. Short Q&A → text only in chat.
5. Long Q&A (>4000 chars) → auto docx link.
6. "Give me word file" → docx generated.
7. Conversations persist across refresh.
8. CLI still runs via `python main.py`.

Test matrix: [testing.md](./testing.md) §7

---

## 6. Traceability

| Requirement | Backend | Frontend | Tests |
|-------------|---------|----------|-------|
| AUTH-* | `backend/auth/` | `frontend/auth/` | Manual |
| ING-* | `services/ingestion_service.py` | `App.tsx` | `test_logging_contract` |
| CHAT-* | `services/chat_service.py` | `App.tsx`, `MessageBubble` | `test_llm_and_parser` |
| EXP-* | `services/export_policy.py` | `MessageBubble` | `test_export_policy` |
| UI-* | — | `frontend/src/` | Manual |
| NFR-* | `middleware/`, `api/main.py` | `vite.config.ts` | — |

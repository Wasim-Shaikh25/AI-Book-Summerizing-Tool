# Code Reference — Services & Pipeline Scripts

> **Services:** `backend/services/`  
> **Scripts:** `backend/scripts/` (pipeline-related)  
> **API spec:** [../backend-api.md](../backend-api.md)

---

## Services (`backend/services/`)

| File | Class / symbol | Purpose | Why | Called by |
|------|----------------|---------|-----|-----------|
| `ingestion_service.py` | `IngestionService.ingest_upload` | Web PDF → `run_pipeline` → DB | Thin wrapper; single extract | `api/routes/books.py` |
| `chat_service.py` | `ChatService.send_message` | Intent route → rewrite/Q&A → optional DOCX | Web chat orchestration | `api/routes/chat.py` |
| `rag_index_helper.py` | `ensure_rag_index_for_book` | Lazy RAG on first ask | `UPLOAD_SKIP_RAG=true` default | `ChatService`, `AskHandler` |
| `rag_index_helper.py` | `load_book_sections` | Sections from DB + logs | Q&A needs 15d/15e bodies | RAG helper |
| `export_policy.py` | `resolve_export_mode` | When to auto-attach DOCX | Long Q&A vs rewrite rules | `ChatService` |
| `export_policy.py` | `user_requests_word_export` | Regex detect Word request | User explicit export | Policy |
| `title_service.py` | `generate_conversation_title` | First-message title | UX for chat list | `ChatService` |
| `upload_jobs.py` | `create_job`, `update_job`, `complete_job`, `fail_job` | In-memory job status | Upload progress polling (ADR-012) | `books.py`, `ingestion_service` |

---

## Pipeline scripts (`backend/scripts/`)

Canonical names (preferred) delegate to legacy scripts. Full catalog: `backend/scripts/README.md`.

| Canonical | Legacy | Purpose | Why it exists | Key env / inputs |
|-----------|--------|---------|---------------|------------------|
| `pipeline_full_book.py` | `run_full_openai_pipeline.py` | Full PDF → structure → rewrite → **structural cleanup → title sync** → DOCX → quality audit | Primary end-to-end dev script; title sync (`propagate_titles_to_hierarchy`) writes cleaned MD titles into the hierarchy so DOCX + audit AC-04 match the Markdown | `PIPELINE_PDF`, `INGESTION_PROFILE`, `REWRITE_USER_INSTRUCTION`, `NOTES_STRUCTURE_FIX_*` |
| `pipeline_batch_books.py` | `run_batch_pipeline.py` | Pipeline + audit for multiple PDFs | Regression across test books | PDF list in script |
| `export_notes_docx.py` | `reexport_docx.py` | DOCX from hierarchy + rewritten map | Format/theme changes without LLM | `PIPELINE_LOG_DIR`, `NOTES_MD` |
| `audit_notes_quality.py` | `run_notes_quality_audit.py` | Standalone quality audit | Audit without full pipeline | MD/DOCX paths, `NOTES_QUALITY_LLM=0` |
| — | `fix_notes_structure.py` | Post-rewrite MD structural fixer (headings/dedupe/low-grounding) | Same as pipeline step `[3/4]`; standalone re-run on existing MD | `--md`, `--engine hybrid\|minilm\|api`, `--log-dir`, `--merge-duplicates`, `--drop-low-grounding` |
| `run_heading_stages.py` | Re-run title/chapter structure phases on saved logs | Iterate hierarchy without re-ingest | `logs/run_*/` |
| `run_15f_cleanup.py` | `clean_titles` only on saved `group_chapters` | Benchmark heading cleanup | Log dir arg |
| `run_15e_test.py` | `group_chapters` + optional sample rewrite | Chapter hierarchy dev | `partition_sections` artifact |
| `run_15g_validation.py` | 15g on saved hierarchy | Title validation dev | 15f/15j artifact |
| `run_notes_quality_audit.py` | Standalone quality audit | Audit without full pipeline | MD/DOCX paths |
| `compare_notes_quality.py` | Compare audits across runs | Regression diff | Output dir |
| `compare_runs.py` | Summarize log run metadata | Debug run folders | `logs/` |
| `rewrite_missing_sections.py` | Fill gaps + re-export | Recovery after partial rewrite | `rewritten_map` |
| `build_rewritten_sidecar.py` | Build `rewritten_map` from MD | Re-export without LLM | Existing `.md` |
| `reexport_docx.py` | DOCX from hierarchy + map | Format/theme changes only | Log dir + MD |
| `export_universal_docx.py` | MD → DOCX with theme env | Quick format test | `.md` file |
| `bench_15f_cleanup.py` | Benchmark 15f modes | rules vs MiniLM vs cloud | 15e logs |
| `run_e2e_scenarios.py` | Rewrite + Q&A scenarios | Integration smoke | Configured books |
| `run_upgrade_validation.py` | `fast_local` structure + sample rewrite | Profile validation | `INGESTION_PROFILE` |
| `audit_headings.py` | Heading quality on hierarchy JSON | Debug structure | 15j artifact |
| `audit_section_topics.py` | Topic classification + PDF match | Section topic debug | Hierarchy + PDF |
| `migrate_runtime_to_root.py` | Move logs/output to repo root | One-time migration | Paths |

---

## API routes (summary)

| Route file | Endpoints | Purpose | Why |
|------------|-----------|---------|-----|
| `api/main.py` | `GET /health` | Liveness | Deploy checks |
| `api/routes/auth.py` | OAuth, guest, `/me` | Authentication | Web platform |
| `api/routes/books.py` | `POST /upload`, `GET /books`, job status | PDF ingest | User books |
| `api/routes/chat.py` | conversations, `POST /message`, SSE stream | Chat + rewrite | Core product |
| `api/routes/exports.py` | `GET /download/{id}` | Download DOCX | Export delivery |

Full request/response schemas: [../backend-api.md](../backend-api.md), `api/schemas.py`.

# Change Log

> Every code or spec change MUST be appended here with: **What / Why / Impact**.
> Most recent entry on top.
> MESO Rules: 2, 6, 10.

---

## [2026-06-07] — Ingestion / TOC / Advanced RAG strategy doc

- **What:** Added `ingestion-toc-rag-strategy.md` — analysis of current structure-first pipeline (15a–15f), RAG gaps, Advanced RAG guide mapping, two-track architecture, phased roadmap.
- **Why:** User requested readable MD for ingestion vs dynamic TOC vs Advanced RAG feasibility.
- **Impact:** Linked from `index.md` supplementary specs and quick navigation.

---

## [2026-06-07] — Spec deduplication (single source of truth)

- **What:** Enforced document hierarchy in `index.md`. Slimmed `api.md` to link index, `overview.md` to executive summary, `architecture.md` (removed pipeline/web/storage duplicates), `requirements-web-platform.md` to requirement IDs only. Module specs link to authoritative parents for schemas/config. Added role headers to `backend-api.md`, `frontend.md`, `data-models.md`, `ui-backend-integration.md`.
- **Why:** Parent specs and module specs repeated the same content in 3+ places; maintenance required updating multiple files per change.
- **Impact:** Each topic has one authoritative file. Other specs link only — edit one place per topic.

---

## [2026-06-07] — Sync specs/modules/ with codebase

- **What:** Updated 5 stale module specs (`structure-extraction`, `toc-persistence`, `logging-debug`, `rag-retrieval`, `parameters-config`) with correct `backend/src/modules/` paths, removed references to deleted code (`toc_splitter`, `TopicRepository`), added final_structuring files, log artifact table, and web platform config. Minor update to `export.md` (added `docx_notes_exporter`, `markdown_docx_renderer`).
- **Why:** Module specs were partially out of sync after v2.0 overhaul — 5 of 11 still used old `src/` paths and missing files.
- **Impact:** All 11 `specs/modules/*.md` files now match `backend/src/modules/` structure.

---

## [2026-06-07] — Remove redundant spec files

- **What:** Deleted `SDD.md` (duplicate of `index.md`), `tasks-ocr-stage.md` (completed OCR checklist), and `specs/README.md` (duplicate navigation). Merged SDD role into `index.md` header + quick start. Fixed `ai-agent-workflow/` links to point at `specs/index.md`.
- **Why:** User requested cleanup; three files added no unique content beyond `index.md`.
- **Impact:** Single entry point is `specs/index.md` only. OCR docs remain in `requirements-ocr-stage.md` and `modules/ingestion.md`.

---

## [2026-06-07] — Comprehensive specs overhaul (v2.0)

- **What:** Rewrote and expanded entire `/specs` folder: new docs (`frontend.md`, `backend-api.md`, `testing.md`, `ui-backend-integration.md`, `future-modifications.md`); updated all core specs (`architecture.md`, `overview.md`, `api.md`, `data-models.md`, `SDD.md`, `index.md`) and module specs with correct `backend/src/modules/` paths, mermaid diagrams, code snippets, test case matrices, UI↔backend contracts, and future modification guides.
- **Why:** User requested full architectural documentation covering UI, backend, engine, tests, diagrams, and best practices for future modifications.
- **Impact:** `/specs` is now the complete SDD. Start at `index.md` for any task. Web platform fully documented alongside engine modules.

---

## [2026-06-01] — Backend monolith layout (clean repo root)

- **What:** Moved `src/`, `tests/`, `scripts/`, `config/`, `main.py`, `pytest.ini` into `backend/`. Merged `requirements.txt`. Flattened web imports (`auth`, `api`, `services` as top-level packages under `backend/`). Root keeps only `backend/`, `frontend/`, `specs/`, runtime data dirs, and deploy files.
- **Why:** User requested full web production stack inside `backend/` with a clean root.
- **Impact:** Run everything from `backend/` (`python main.py`, `uvicorn api.main:app`, `pytest`). Set `PROJECT_ROOT` env for non-standard data paths. Docker uses repo mount at `/workspace`.

---

## [2026-06-01] — Web platform Phase 1–2 + legacy cleanup

- **What:** Added `backend/` (FastAPI, OAuth, chat API, SSE streaming, rate limits), `frontend/` (React chat UI), `specs/requirements-web-platform.md`. Removed legacy compat shims (`src/interaction`, `src/ingestion`, `src/storage`, `src/structure`, `src/generation`, `src/debug`, `src/export`, `src/core`, `src/app`, `src/domain`), obsolete `doc/spec/`, and dead modules (`content_generation`, `ingestion/service`, `question_paper_handler`, `topic_repository`, `toc_splitter`). Docker compose scaffold added.
- **Why:** User requested web UI with auth, chat history, Word export policy; legacy shims had zero imports and duplicated canonical `src/modules/` paths.
- **Impact:** Use `python -m backend.api.main` + `frontend npm run dev`. CLI unchanged via `main.py`. Import only from `src.modules.*` / `src.shared.*`. Full-book rewrite always exports Word.

---

## [2026-05-31] — Page OCR stage for scanned / two-up PDFs

- **What:** `ocr_stage.py`, extended `OCRReader.extract_lines_from_region`, wired into `extract_pdf`; config keys `OCR_*` + `TESSERACT_CMD`; layout sort by `(y0, x0)`.
- **Why:** Full-page scans and two-up spreads had no text layer; prior pipeline skipped OCR on large images.
- **Impact:** Enable `OCR_SPLIT_TWO_UP=true` for left/right book pages on one PDF page; requires Tesseract installed.

---

## [2026-05-31] — RAG schema migration + index path fix

- **What:** `RagRepository` drops legacy `rag_chunks` when old columns (e.g. `text_hash`) are present; `RagService` uses `Path` for `RAG_INDEX_DIR`.
- **Why:** Existing DB had incompatible schema causing `NOT NULL constraint failed: rag_chunks.text_hash`; index meta save crashed on str `/` book_id.
- **Impact:** Index build completes (182 chunks on Torts book); hybrid retrieval works; E2E Q&A uses vector RAG when `book_id` is set.

---

## [2026-05-31] — Vector RAG for Q&A (FAISS + hybrid retrieval)

- **What:** `src/modules/rag/` (chunk builder, FAISS indexer, hybrid retriever), `RagRepository`, wired into `BookQaEngine` and post-ingestion index build.
- **Why:** Keyword-only Q&A missed semantic matches; user requested vector RAG.
- **Impact:** Q&A uses MiniLM + FAISS with lexical fusion; index auto-builds after ingestion.

---

## [2026-05-31] — E2E Q&A + scenario tests wired

- **What:** `BookQaEngine` + `AskHandler` for topic/scenario Q&A; intent parser detects explain/revision/exam modes; `scripts/run_e2e_scenarios.py` runs 5 end-to-end tests.
- **Why:** CLI previously refused Q&A; user requested full scenario validation (rewrite modes + explain topics + domain guard).
- **Impact:** After ingestion, users can ask `explain ...` questions; scenario tort questions answered, unrelated subjects refused.

---

## [2026-05-31] — Fix DOCX TOC page numbers (build order)

- **What:** `docx_notes_exporter.py` now builds cover → TOC → chapters in final order (no TOC prepend after body). Improved Word COM field refresh for PAGEREF.
- **Why:** Prepending TOC after chapters left stale PAGEREF page numbers (often matching PDF-like low pages instead of real DOCX pages).
- **Impact:** Re-exported DOCX files get correct TOC pagination; requires `pywin32` on Windows for auto field refresh.

---

## [2026-05-28] — Repo cleanup after hierarchical DOCX export

- **What:** Added `models/README.md`, gitignore for local GGUF weights, removed stray `models/BIT632.tmp`.
- **Why:** Keep repository lean; model binaries belong on disk only.
- **Impact:** Clone stays small; operators place GGUF files under `models/` locally.

---

## [2026-05-28] — Stage 15e + structured Word export with TOC page numbers

- **What:**
  - `chapter_hierarchy_builder.py` (15e) with LLM + rule fallback and consolidation.
  - `docx_notes_exporter.py`: cover, hierarchical TOC (PAGEREF), footer page numbers, Word COM field refresh (`pywin32`).
  - Pipeline scripts: `run_full_openai_pipeline.py`, `reexport_docx.py`.
  - Fixed TOC block insertion order and field update (no premature unlink).
- **Why:** Full-book notes need chapter hierarchy and accurate Word TOC page numbers.
- **Impact:** Export produces formatted DOCX; requires `pywin32` on Windows for auto TOC pagination.

---

## [2026-05-27] — Stages 2–4: LLM hardening, CLI/export, plugin pipeline

- **What:**
  - Stage 15b wired: `stage_15b.py`, encoder modules, logs `15b_*` JSON stages.
  - Plugin pipeline: `context.py`, `stages.py`, thin `runner.py`.
  - `RewriteEngine` + `RewriteHandler` + `ExportHandler` + `CommandLoop` wiring.
  - Unit tests: `test_llm_and_parser.py`, `test_pipeline_stages.py`.
  - Updated `.env.example`, `parameters-config.md`, `architecture.md`, `tasks.md`.
- **Why:** Complete MESO roadmap stages 2–4.
- **Impact:** Rewrite/export work post-ingestion; doubted sections resolved when late TOC detected.

---

## [2026-05-27] — Stage 1: Tests restored + legacy stubs cleaned

- **What:**
  - Restored 4 test modules under `tests/unit/` and `tests/integration/` with MESO import paths.
  - Added `tests/conftest.py` (fixture PDF + isolated log cwd).
  - Updated expected stage JSON set (`13_visual_elements`, `14_doubted_sections`).
  - Refactored CLI handlers to stubs without imports of removed legacy modules.
  - Fixed `14_doubted_sections.json` envelope: log payload wrapped as list for schema consistency.
- **Why:**
  - Stage 1 spec ⇄ code alignment; restore regression safety after MESO refactor.
- **Impact:**
  - Run `pytest tests/unit` for fast checks; `pytest tests/integration -m integration` for pipeline contract.

---

## [2026-05-27] — MESO Project Structure Refactor

- **What:**
  - Introduced MESO layout: `config/default.yaml`, `src/shared/`, `src/modules/`.
  - Moved ingestion, structure, storage, generation, export, interaction, debug into `src/modules/`.
  - Moved pipeline orchestrator to `src/modules/pipeline/runner.py`; models to `src/shared/models.py`.
  - Added `src/shared/config.py` YAML+env loader; `src/config.py` and old package paths kept as compat shims.
  - Added `docs/README.md`; updated `spec/architecture.md`, traceability matrix.
  - Added `PyYAML` dependency for config loading.
- **Why:**
  - Align codebase with MESO Universal Engineering Standard (Rule 12 config centralization, module mirroring).
- **Impact:**
  - **Canonical imports:** `src.modules.*`, `src.shared.*`.
  - **Legacy imports still work** via thin shims at `src/ingestion/`, `src/structure/`, etc.
  - Debug entry: `python -m src.modules.debug.run_toc_trace` (shim: `python -m src.debug.run_toc_trace`).

---

## [2026-05-27] — MESO Bootstrap

- **What:**
  - Created MESO-compliant `/spec/` tree: `index.md`, `SDD.md`, `overview.md`, `architecture.md`, `api.md`, `data-models.md`, `change-log.md`, `unused-tracking.md`.
  - Added `/spec/modules/` (10 module specs mapped from `doc/spec/` + codebase).
  - Created `/ai-agent-workflow/` with `requirements.md`, `tasks.md`, `SDD.md`.
  - Created `/tests/` skeleton directories (`unit/`, `integration/`, `fixtures/`).
- **Why:**
  - User triggered MESO Rule 10 — spec must precede code and serve as single source of truth.
  - Existing `doc/spec/` call-chain docs superseded by authoritative `/spec/`.
- **Impact:**
  - All future changes must update `/spec` first, then code, then tests, then this log.
  - `doc/spec/` retained as legacy reference only.

---

## [2026-05-27] — In-flight code changes (pre-MESO, untracked/partial)

- **What:**
  - New LLM modules: `src/core/llm_chat_client.py`, `src/generation/model_router.py`, final structuring resolver/revalidation.
  - Config expansion in `src/config.py`, `.env.example`, `requirements.txt`.
  - Tests deleted: `test_continuity_and_gate.py`, `test_fragment_coverage.py`, etc.
- **Why:**
  - OpenAI/local LLM pipeline integration and doubted-section resolver work in progress.
- **Impact:**
  - Spec modules `llm-generation.md` and `parameters-config.md` document intended state; test coverage gap tracked in SDD §4.

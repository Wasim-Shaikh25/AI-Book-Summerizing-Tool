# Change Log

> Every code or spec change MUST be appended here with: **What / Why / Impact**.
> Most recent entry on top.
> MESO Rules: 2, 6, 10.

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

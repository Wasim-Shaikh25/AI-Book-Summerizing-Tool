# Tasks — AI Notes Creator

> Checklist derived from [change-plan-local-ingestion.md](./change-plan-local-ingestion.md).  
> **Status: all phases complete** (2026-06-07).

---

## Stage 6 — Local ingestion & performance ✅

### Phase 0 — Performance
- [x] Fix double `extract_pdf`
- [x] `stage_registry.py` + canonical `s01`–`s16`
- [x] `LOGS_FOLDER` / path constants + `.gitignore`
- [x] `ingestion.profile` (`fast_local` | `quality_cloud` | `debug`)
- [x] Lazy RAG on first ask
- [x] Per-stage upload progress
- [x] OCR zoom 1.5 for `fast_local`

### Phase 1 — Local structure
- [x] BigBird + fast 15b/15e via `fast_local` profile
- [x] `IngestionService` profile context

### Phase 2 — FLAN-T5 15f
- [x] `flan_title_cleaner.py` + MiniLM pick
- [x] `bench_15f_cleanup.py`

### Phase 3–4 — RAG
- [x] Cross-encoder rerank (`reranker.py`)
- [x] Context builder with citations (`context_builder.py`)

### Phase 5 — Registry
- [x] `STAGES` from `get_pipeline_stages()`
- [x] Progress IDs in registry

### Phase 6 — Structure
- [x] PDF bookmark TOC fallback
- [x] Semantic section boundaries (MiniLM coherence)

### Phase 7 — Folder shims
- [x] `backend/engine/`, `backend/web_platform/`, `backend/app/`

---

## Notes quality P0 — Coverage (2026-06-15) ✅

Per [change-plan-notes-quality.md](./change-plan-notes-quality.md):

- [x] `document_profile.py` — measured profile + `s00_document_profile.json`
- [x] Pipeline stage `stage_compute_document_profile`
- [x] `build_ultimate_sections` uses `profile.min_section_body_chars`
- [x] `EXPORT_MISSING_BODY_MODE` (placeholder default)
- [x] Inline auto-retry in `RewriteEngine.rewrite_sections`
- [x] Tests: `test_document_profile.py`, `test_export_missing_body_mode.py` (287 passed)
- [x] Specs + change-log updated

### Notes quality P1 — Fidelity ✅

- [x] `rewrite_fidelity.py` + post-rewrite overlap gate in `parallel_rewrite`
- [x] Display-layer heading guard in `document_formatter`
- [x] PDF-anchored title acceptance (`title_pdf_anchor.py`)
- [x] Quality report document profile + rewrite summaries
- [x] Tests: `test_rewrite_fidelity.py`

### Notes quality P2 — Mirrors ✅

- [x] 1-section parent-mirror collapse in `fix_parent_mirror_chapters`
- [x] Tests: `test_chapter_single_section_mirror.py`

### Notes quality P3 — Remove density rule + post-rewrite structural fixer (2026-06-15) ✅

- [x] Removed sentence-length / "dense prose" audit rule (`assess_body_simplicity`, `readability` dimension, report §14, `simplicity_*` wiring)
- [x] New `generation/notes_structure_fix.py` — heading repair (hybrid LLM/MiniLM), duplicate flag/merge, low-grounding flag/drop; body prose never edited; TOC regenerated
- [x] Standalone `scripts/fix_notes_structure.py` (`--engine`, `--log-dir`, `--merge-duplicates`, `--drop-low-grounding`)
- [x] Tests: `test_notes_structure_fix.py` (8); validated on bareact-140 (bodies byte-identical, 1 chapter title repaired, 17 low-grounding flagged)
- [x] Wired fixer into `run_full_openai_pipeline.py` as step `[3/4]` via `structure_fix_runner.py` (default on)
- [ ] Optional: full re-audit on the LLM (`--engine hybrid` with provider) to confirm AC-04 PASS after chapter-title repair

### Notes quality P4 — Upstream grounding fix (partition gate + contents-page detection) (2026-06-15)

- [x] Shared `src/shared/text_grounding.py` primitives; `rewrite_fidelity.py` delegates (public API unchanged)
- [x] Option B — partition grounding gate in `book_assembler.build_ultimate_sections` (`PARTITION_DROP_LOW_GROUNDING`, `meta.low_grounding_dropped`)
- [x] Option A — `structure/contents_region.py` + `stage_detect_toc` wiring (`CONTENTS_REGION_DETECTION`)
- [x] Tests: `test_text_grounding.py` (11), `test_contents_region.py` (4), +1 `test_ultimate_sections.py`
- [x] Cheap validation on bareact-140 artifacts: 18 index pages flagged, 116 low-grounding sections dropped (all verified index/table/empty)
- [x] Full pipeline re-run on bareact-140 (run_2026-06-15_09-22-35): coverage 56/56 (100%); low_grounding 17→7; sections →56 (no coverage loss); **fidelity WARN→OK, repetition WARN→PASS**
- [x] Post-rewrite `fix_notes_structure.py` on fixed MD cleared heading noise (export violations 8→0, AC-02/03 PASS, heading_acceptance WARN→OK)
- [x] Wired `structure_fix_runner` into `run_full_openai_pipeline.py` as step `[3/4]` (default on; before DOCX + audit)
- [x] Audit recalibration (semantic line grounding + source-grounded PDF titles): `line_quality` WARN→OK (issues 46→1), **OVERALL WARN→OK**
- [ ] `pdf_match` still WARN (11 failures) — honestly flags noisy titles on ~7 residual index-derived sections; clearing requires upstream handling of those sections, not metric relaxation

### Notes quality P5 — Title sync to DOCX + audit hierarchy (2026-06-15)

- [x] Debugged residual `bareact-140` OVERALL WARN: all `heading_acceptance` violations were `export_docx`/`hierarchy_*`, zero `export_md` — the fixer edited only Markdown while DOCX rendered raw `hierarchy['heading']` and audit AC-04 read the raw on-disk artifact
- [x] `structure_fix_runner.propagate_titles_to_hierarchy` — sync final MD titles into in-memory hierarchy (DOCX) + rewrite on-disk hierarchy artifact (audit); sections by `section_id`, chapters by sid-majority vote
- [x] Wired into `run_full_openai_pipeline.py` after structural cleanup, before DOCX export + audit
- [x] Tests: `test_structure_fix_runner.py` (+4 propagation cases)
- [x] Validated on real bareact-140 artifacts (run_2026-06-15_11-21-16 + 11-25-37 MD): `heading_acceptance` violations **14 → 0** (export_docx 8→0, hierarchy_display 4→0, hierarchy_raw 2→0; AC-02/03/04 all clear); 21 titles synced
- [x] Fixed pre-existing loader bug: `load_chapter_hierarchy_json` now accepts both `{items:{chapters}}` (s15f) and top-level `{chapters}` (s15j) schemas (`test_toc_sections.py`, 4 tests)
- [x] **End-to-end run on bareact-140.pdf (run_2026-06-15_12-07-50): OVERALL OK** — coverage 56/56, heading_acceptance **WARN→PASS** (0 export violations), line_quality PASS; on-disk s15j headings synced to clean topic titles; only `pdf_match` WARN remains (honest: cleaned topic titles not verbatim in bare-act PDF)

---

## Notes quality & hierarchy (2026-06-13) — Partial

### Implemented
- [x] Quality module (`backend/src/modules/quality/`)
- [x] Heading acceptance AC-01…AC-05, AC-07
- [x] Line-by-line audit (D11)
- [x] `notes_body_postprocess.py` post-rewrite cleanup
- [x] `enforce_chapter_structure()` wired at 15g/15i/15j + rewrite
- [x] `is_statute_prose_heading()` for bare-act prose titles
- [x] Unit tests: `test_enforce_chapter_structure`, `test_heading_acceptance`, `test_notes_body_postprocess`
- [x] Specs synced: `specs/modules/quality.md`, `structure-extraction.md`, `change-log.md`
- [x] Full `specs/code-reference/` + rule `13-comprehensive-spec-documentation.mdc`
- [x] Export emits `<!-- sid:SXX -->` on section headings; audit uses `resolve_rewritten_map` (sid-first join)

### Pending verification
- [ ] Full 4-PDF batch re-run after `hierarchy_openai_refinement` import fix
- [ ] Environmental law ≥ 3 chapters in export
- [ ] Bare act AC-03/AC-04 PASS (no statute prose in export titles)

---

## Next (optional / future)

- Full physical move `src/modules` → `engine/` (breaking import migration)
- Fine-tune FLAN-T5 on domain headings
- Docker multi-service (Qdrant) if scale requires

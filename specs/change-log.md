# Change Log

> Every code or spec change MUST be appended here with: **What / Why / Impact**.
> Most recent entry on top.
> MESO Rules: 2, 6, 10.

---

## [2026-06-15] — Hierarchy loader accepts both on-disk schemas + e2e validation

- **What:** `toc_sections.load_chapter_hierarchy_json` now loads both hierarchy schemas: the legacy wrapped form (`{"items": {"chapters": [...]}}`, e.g. `s15f_heading_cleanup.json`) and the cloud-hierarchy form (`{"chapters": [...], "meta": {...}}`, e.g. `s15j_hierarchy_openai.json`). Previously it required the `items` wrapper and raised `Invalid chapter hierarchy payload` whenever `resolve_chapter_hierarchy_artifact` returned `s15j` (which is preferred when the cloud-hierarchy stage runs). The structure-fix title sync (`propagate_titles_to_hierarchy`) also now returns `max(in_memory, on_disk)` updates so the pipeline log reports the disk-only sync case.
- **Why:** Universal/subject-agnostic correctness — the loader must not depend on which optional stage produced the artifact. Schema choice is purely structural, not domain-specific. Discovered while running the title-sync end-to-end.
- **Impact:** Full pipeline runs cleanly when 15j is enabled. End-to-end run on `bareact-140.pdf` (run_2026-06-15_12-07-50): coverage 56/56 (100%), **heading_acceptance WARN→PASS** (0 export violations, AC-01…AC-07 all PASS; on-disk `s15j` headings now clean topic titles), line_quality PASS, **OVERALL OK**. Only `pdf_match` remains WARN (41 cleaned topic titles not verbatim in this bare-act PDF; 5 grounded-in-source) — honest, expected. Tests: `test_toc_sections.py` (4).

---

## [2026-06-15] — Title sync: Markdown titles propagated to DOCX + audit hierarchy

- **What:** Added `propagate_titles_to_hierarchy(fixed_md, hierarchy, *, hierarchy_path)` to `generation/structure_fix_runner.py` and wired it into `run_full_openai_pipeline.py` between the structural cleanup step and DOCX export. It parses the final notes Markdown and writes its section titles (matched by `section_id`) and chapter titles (matched by sid-majority vote, positional fallback only when a chapter has no sids) into both the in-memory hierarchy (used by `DocxNotesExporter`) and the on-disk hierarchy artifact (read by the audit for AC-04).
- **Why:** Debugging the persistent `bareact-140` OVERALL WARN showed the structural fixer only edited the Markdown string, while the **DOCX** export rendered raw `hierarchy['heading']` (`docx_notes_exporter.py`) and the **audit AC-04** read the raw on-disk hierarchy artifact (`analyzer.py`). All `heading_acceptance` violations were `export_docx`/`hierarchy_*` with **zero** `export_md` — i.e. the fix never reached the two graded artifacts. Three title representations (Markdown / DOCX / hierarchy) had diverged.
- **Impact:** DOCX titles and the audit's hierarchy now use the same cleaned/display-resolved titles the reader sees in the Markdown, so `export_docx` (AC-02/AC-03) and AC-04 reflect the repaired titles instead of raw fragments. Honest WARNs remain only for titles the fixer genuinely cannot clean. Tests: `test_structure_fix_runner.py` (+4 propagation cases).

---

## [2026-06-15] — Full pipeline wiring: structural cleanup step [3/4]

- **What:** Integrated post-export structural fixer into `run_full_openai_pipeline.py` / `pipeline_full_book.py`. New `generation/structure_fix_runner.py` centralizes log-dir source loading, LLM chat setup, and `fix_notes_markdown` invocation. Pipeline flow is now `[1/4]` structure → `[2/4]` rewrite/assemble → `[3/4]` structural cleanup → DOCX export → `[4/4]` quality audit. `fix_notes_structure.py` delegates to the same runner. Config: `export.structure_fix_enabled` (`NOTES_STRUCTURE_FIX_ENABLED`, default true), `structure_fix_engine` (`hybrid`), `structure_fix_merge_duplicates`, `structure_fix_drop_low_grounding`.
- **Why:** User requested all new stages/scripts interconnected so a single full pipeline run triggers everything — structural fixer was the only remaining standalone piece.
- **Impact:** Default full run repairs noisy headings, renumbers lists per topic, writes `<stem>.structure_fix.json`, then exports DOCX and audits the **fixed** markdown. Disable with `NOTES_STRUCTURE_FIX_ENABLED=0`. Tests: `test_structure_fix_runner.py` (3).

---

## [2026-06-15] — Ordered-list numbering restarts per topic/section

- **What:** Fixed numbered lists continuing across topics (topic A ends at 5, topic B wrongly showed 6, 7…). (1) `markdown_format_normalizer.renumber_ordered_list_blocks` restarts `N.` lines at 1 for each separate list block; wired into `strict_normalize_markdown`, `postprocess_rewritten_section`, and `notes_structure_fix.render_notes_md`. (2) DOCX export: `docx_theme.restart_numbered_paragraph` + `NumberedListTracker` restart Word `List Number` at each new section body (`note_body_docx`) and at `#`/`##`/`###` boundaries (`markdown_docx_renderer`).
- **Why:** User: when one topic has points 1–5, the next topic must start again from 1 — not continue numbering from the previous topic.
- **Impact:** Applies on rewrite, structural fixer output, and DOCX export. Tests: +3 `test_markdown_format_normalizer.py`, +2 `test_note_body_docx.py`.

---

## [2026-06-15] — Audit recalibration: semantic line grounding + source-grounded PDF titles

- **What:** Reframed two quality metrics from **literal string matching** to **meaning/source grounding** so they stop penalizing the desired improvements (cleaned titles + simple-English paraphrase) while still catching real drift. (1) `line_audit.py`: a line failing the literal `low_source_overlap` check now gets a semantic second chance via the shared MiniLM encoder (`_SemanticGrounder`, `NOTES_QUALITY_SEMANTIC_GROUNDING` default on, `NOTES_QUALITY_SEMANTIC_MIN_SIM` default 0.45) — high embedding similarity to any source sentence suppresses the flag; genuinely drifted lines (low semantic sim) are still flagged. Sections whose source is itself low-grounding (`text_grounding.is_low_grounding`) skip the overlap/`section_drift` checks entirely (already reported separately — no double-penalty). (2) `analyzer.py` `pdf_match_heading`: a clean (`looks_ok`) title absent from the PDF but whose content words are covered by its section source returns new status `grounded_in_source` (≥ 60 % token coverage, `NOTES_QUALITY_PDF_MATCH_SOURCE_GROUNDING` default on) and is not counted as a match failure; noisy titles and title/source mismatches still fail.
- **Why:** After the upstream grounding fix + structural fixer, the only residual WARNs were `line_quality` (paraphrase lowers literal token overlap) and `pdf_match` (cleaning a title removes its verbatim PDF substring) — measurement side-effects of the very improvements requested, not content defects. User approved recalibrating both to semantic/source grounding rather than leaving false-signal WARNs.
- **Impact:** Env: `NOTES_QUALITY_SEMANTIC_GROUNDING`, `NOTES_QUALITY_SEMANTIC_MIN_SIM`, `NOTES_QUALITY_PDF_MATCH_SOURCE_GROUNDING`. Re-audit of bareact-140 fixed notes: **`line_quality` WARN → OK** (line issues 46 → 1, FAIL sections 11 → 0 — paraphrase accepted, worst sections now score 94), **OVERALL WARN → OK**. `pdf_match` improved (failures 13 → 11) but **remains WARN honestly** — the 11 are genuinely noisy titles (`Section topic — CHAPTER I`, PDF fragments) / title-source mismatches on the residual index-derived sections, which the recalibration correctly did **not** suppress. Tests: +4 in `test_line_audit.py`, +3 in `test_notes_quality_audit.py`. Clearing `pdf_match` requires upstream handling of the ~7 residual low-grounding sections, not further metric relaxation.

---

## [2026-06-15] — Upstream grounding fix: partition gate + contents-page detection

- **What:** Fixed the low-grounding sections at their **source** (the ingestion/partition pipeline) instead of post-processing. (1) New shared module `src/shared/text_grounding.py` holds the subject-agnostic primitives (`ENUM_TITLE_LINE_RE`, `is_enumerated_title_line`, `real_content_chars`, `enumerated_line_ratio`, `is_low_grounding`, `is_contents_listing`); `generation/rewrite_fidelity.py` now delegates to it (public API `source_real_content_chars` / `source_is_low_grounding` / `resolve_min_grounding_chars` unchanged). (2) **Option B — partition grounding gate:** `book_assembler.build_ultimate_sections` no longer emits a rewrite section when its reconstructed body is an index/contents listing (`is_contents_listing`: enumeration-dominated or < 40 real chars); count surfaced as `meta.low_grounding_dropped`. Behind `PARTITION_DROP_LOW_GROUNDING` (default on). (3) **Option A — document-wide contents-page detection:** new `structure/contents_region.py` (`detect_contents_regions`) flags any page whose non-noise lines are ≥ 50 % enumerated title rows (≥ 5 rows); `stage_detect_toc` unions those line ids into `toc_section_line_ids` so their headings are excluded from partitioning (not just the front-matter TOC). Behind `CONTENTS_REGION_DETECTION` (default on).
- **Why:** Earlier audit/structural-fixer work left `line_quality` WARN, `pdf_match` WARN and AC-04 driven by ~17 sections sourced from mid-document index/contents pages. The structural fixer can only flag these after rewrite; the root cause is partition emitting them. User asked to fix it upstream and to combine both approaches (A + B).
- **Impact:** Config/env: `structure.partition_drop_low_grounding` (`PARTITION_DROP_LOW_GROUNDING`, default true), `structure.contents_region_detection` (`CONTENTS_REGION_DETECTION`, default true). Tests: new `test_text_grounding.py` (11), `test_contents_region.py` (4), `+1` in `test_ultimate_sections.py`; full suite collects 320. **Full pipeline re-run + re-audit on bareact-140 (run_2026-06-15_09-22-35):** rewrite coverage 56/56 (100%, 0 missing/empty/unmapped); `low_grounding_sections` **17 → 7**; sections ~66–77 → **56** with no coverage loss (0 page-order inversions); verdict deltas: **fidelity WARN → OK**, **repetition WARN → PASS**. Residual WARNs (`line_quality`, `pdf_match`, `heading_acceptance`) are now concentrated in noisy heading *text* (AC-02/03/04 — handled by the post-rewrite structural fixer) and paraphrase-driven low line-overlap, not ungrounded bodies.

---

## [2026-06-15] — Removed prose-density audit rule + post-rewrite structural fixer

- **What:** (1) Removed the sentence-length / "dense prose" rule from the quality audit — deleted `assess_body_simplicity` (function, export, tests), the `readability` verdict dimension, the report §14 readability block, and all `simplicity_*` fields/wiring in `analyzer.py`, `heuristics.py`, `models.py`, `llm_insights.py`, `run_batch_pipeline.py`. (2) Added a new post-rewrite structural cleanup module `generation/notes_structure_fix.py` + standalone script `scripts/fix_notes_structure.py`. It parses the exported notes Markdown, **repairs noisy `#`/`##`/`###` titles** (titles that fail `classify_heading`) by deriving a clean topic title from the already-clean body — hybrid engine: one batched LLM call when chat is enabled, MiniLM-from-body + `ensure_study_safe_heading` floor offline; **flags (opt-in `--merge-duplicates`) near-identical adjacent sections**; **flags (opt-in `--drop-low-grounding`, needs `--log-dir`) index/contents-style sections** via `source_is_low_grounding`. Section body prose is never edited; the Table of Contents is regenerated from repaired headings. A JSON change report records engine, models, and every before→after for provenance.
- **Why:** User: text density / long sentences are not a quality problem (stop auditing them); the real remaining defects are structural — fix them with a post-processing pass using MiniLM/API. Detection stays fully subject-agnostic (structural heading classifier + embedding similarity + measured grounding only).
- **Impact:** No new config/env keys (script is standalone, defaults non-destructive). Validated on bareact-140: 11→11 chapters, 77→77 sections, **all section bodies byte-identical**, 1 noisy chapter title repaired, 17 low-grounding sections flagged. Tests: new `test_notes_structure_fix.py` (8); `assess_body_simplicity` tests removed (305 passed). Default `engine=hybrid` falls back to offline when no LLM provider.

---

## [2026-06-15] — Source-grounding fidelity guard + subject-hardcoding removal

- **What:** Root-caused low fidelity (13–21% overlap, drift): ~77% of sections had **index/contents-style source spans** (page-of-titles, ~160–200 chars), so the model expanded from prior knowledge. Added measured, subject-agnostic detection in `rewrite_fidelity.py` (`source_real_content_chars`, `source_is_low_grounding` via enumeration ratio + letter count; `resolve_min_grounding_chars`). `parallel_rewrite` now forces strict source-only mode (zero neighbour context, strict prefix) from the first attempt for low-grounding sources and counts them (`low_grounding_sections` stat). Audit (`analyzer.py`) reconstructs the **exact rewrite source** from layout lines (`toc_sections.build_source_text_by_id` / `line_text_map_from_records`) instead of the truncated 160-char preview, reports all-vs-grounded overlap + low-grounding count, and the fidelity verdict now uses grounded overlap (index/contents sources excluded as non-actionable). Removed subject-specific hardcoding from `dropped_heading_registry.is_generic_study_title` (dropped `_FAMILY_LAW_ROMAN_RE`, the `LAW` token in `_SUBJECT_CAPS_RE`, and the `family law / muslim law / environmental law / constitutional law / article` literal set; kept only structural-generic terms).
- **Why:** User: fix remaining quality issues with **no subject-specific hardcoding anywhere**. Investigation (S20: heading "Punishment for bribery", source = "169. Candidate… 170. Bribery…" index list) confirmed a structural source-capture gap, not a measurement artifact or rewrite bug.
- **Impact:** Config: `rewrite.min_grounding_chars` (env `REWRITE_MIN_GROUNDING_CHARS`, default 160). Fidelity now measured honestly against real source; low-grounding sources surfaced and de-weighted; less hallucinated expansion. Tests: +4 in `test_rewrite_fidelity.py`; `test_generic_study_titles.py` made subject-agnostic (299 passed). Note: section-level structure fix (not emitting sections from mid-document contents pages) remains a larger follow-up.

---

## [2026-06-15] — Audit mapping fix + batch profile wiring

- **What:** `assemble_notes_document` no longer strips `<!-- sid:SXX -->` anchors from saved markdown (DOCX render still strips). `parse_markdown_sections` reads `###` sid tags for bundled export. Quality analyzer prefers `.rewritten.json` sidecar when present. `run_full_openai_pipeline.py` loads `document_profile` from logs for overlap/tokens/single-topic prompt; persists `rewrite_fidelity_summary` / `rewrite_auto_retry_summary` to hierarchy JSON. `ensure_study_safe_heading` repairs weak display titles before export.
- **Why:** bareact-140 re-run showed 77/77 rewrite validation but only 39/77 audit SID mapping; batch script ignored profile overlap (600 vs 9).
- **Impact:** AC-05 completeness should reflect sidecar; audit join works from markdown sid tags. Tests: +3 in `test_rewrite_validation.py`, +1 in `test_heading_title_engine.py` (295 passed).

---

## [2026-06-15] — Notes quality P1/P2: fidelity gate, heading guard, PDF titles, mirrors

- **What:** `rewrite_fidelity.py` shares overlap scoring with `line_audit.py`; `parallel_rewrite` regenerates low-overlap sections once with strict prompt and zero neighbour context. Export display guard uses `classify_heading` + `partition_heading_to_study_title`. `title_pdf_anchor.py` gates LLM-edited titles when `require_strict_heading_match`. Wired through `hierarchy_openai_refinement`, `run_heading_refinement`, `heading_title_engine._cloud_title_fallback`. Single-section parent-mirror collapse in `fix_parent_mirror_chapters`. Quality report shows document profile + auto-retry/fidelity summaries.
- **Why:** Complete change-plan-notes-quality.md P1/P2 without subject-specific logic.
- **Impact:** Config: `rewrite.fidelity_min_overlap`, `rewrite.fidelity_regenerate_temperature`. Tests: `test_rewrite_fidelity.py`, `test_chapter_single_section_mirror.py` (292 passed).

---

## [2026-06-15] — Notes quality P0: document profile + coverage fixes (subject-agnostic)

- **What:** New `document_profile.py` computes measured document shape signals and derived tuning knobs (`min_section_body_chars`, `rewrite_overlap_chars`, `rewrite_max_tokens`, etc.). Pipeline stage `stage_compute_document_profile` writes `s00_document_profile.json` (log key `document_profile`). `build_ultimate_sections` reads profile min-body threshold. Export `EXPORT_MISSING_BODY_MODE` (`placeholder` \| `fail` \| `skip`) stops silent section drops. `RewriteEngine.rewrite_sections` runs inline auto-retry when coverage &lt; `REWRITE_AUTO_RETRY_MIN_COVERAGE`. Config keys in `document_profile`, `rewrite.auto_retry_*`, `export.missing_body_mode`.
- **Why:** bareact-140 quality report — 39% coverage, silent export drops, no inline retry; user requires universal (non-subject) adaptation.
- **Impact:** New pipeline stage (15 total). Default export preserves all hierarchy sections with placeholder text. Tests: `test_document_profile.py`, `test_export_missing_body_mode.py` (287 passed). P1 (fidelity gate) and P2 (mirror fix) pending.

---

## [2026-06-15] — Spec sync: semantic stage names across module specs

- **What:** Updated authoritative specs for semantic log keys: `pipeline-core.md`, `logging-debug.md`, `structure-extraction.md`, `stage-catalog.md`, `architecture.md`, `parameters-config.md`, `code-reference/pipeline.md`, `code-reference/services-scripts.md`. Added log-key column to logging-debug artifact table; replaced 15x references with `group_chapters`, `resolve_doubted_toc`, etc.
- **Why:** User asked whether specs were updated after stage rename — several files were still stale.
- **Impact:** `stage-catalog.md` is the single human-readable name map; other specs link to it. Historical `change-log.md` entries retain old 15x names as audit trail.

---

## [2026-06-15] — Semantic log keys replace 15a–15j numeric stage IDs

- **What:** Canonical pipeline log keys renamed from `15e_chapter_hierarchy`, `15b_doubted_resolved`, etc. to semantic names (`group_chapters`, `resolve_doubted_toc`, `partition_sections`, …). `LEGACY_LOG_KEY_ALIASES` + `normalize_log_key()` accept old keys in scripts and old run folders. On-disk filenames unchanged (`s15e_…`, `s15b_…`). New constants: `STAGE_GROUP_CHAPTERS`, `STAGE_PARTITION_SECTIONS`, …; `STAGE_15E` etc. remain deprecated aliases.
- **Why:** User request — meaningful stage names instead of opaque numeric IDs in code and logs.
- **Impact:** New runs write `"stage": "group_chapters"` in JSON envelopes. Old runs still readable via alias resolution. Tests: extended `test_stage_registry.py`, `test_stage_catalog.py` (280 passed).

---

## [2026-06-15] — Semantic stage naming + script catalog + stage-catalog spec

- **What:** Added `stage_catalog.py` with semantic IDs, display names, and legacy function aliases. Renamed all 14 `stages.py` functions (e.g. `stage_ingest_pdf`, `stage_build_book_structure`); deprecated old names kept as aliases. Progress UI uses semantic names; log keys/filenames unchanged. Added canonical script entry points: `pipeline_full_book.py`, `export_notes_docx.py`, `audit_notes_quality.py`, `pipeline_batch_books.py` (delegate to legacy scripts). New docs: `specs/modules/stage-catalog.md`, `backend/scripts/README.md`. Tests: `test_stage_catalog.py`; updated pipeline progress/registry tests.
- **Why:** User request — understandable stage/script names, clarify which steps redo work vs complement each other, consolidate structure orchestration documentation without skipping sub-step functionality.
- **Impact:** Zero log artifact contract change. Imports of `stage_extract` etc. still work. Docs and UI progress are human-readable; developers should prefer canonical script names in new automation.

---

## [2026-06-15] — Structure stage consolidation + fast-path gates (speed + token cost)

- **What:** Consolidated final structuring into `structure_orchestrator.py` (phases A–E; log keys unchanged). Stage 15j now has three cost gates: `_hierarchy_needs_regroup` (skip ~7 min regroup when local chapters healthy), existing names gate, polish gate; `hierarchy_needs_cloud_refinement()` skips entire 15j when all pass. Defaults: `hierarchy_openai.enabled=false`, `auto_skip=true`, `heading_refinement.openai_fallback=false`. Extended `fast_local` ingestion profile to disable 15j, 15b LLM, intent LLM, quality LLM. `run_full_openai_pipeline.py` applies profile, reuses pipeline `lines` (no double PDF extract), wires `cached_generate`.
- **Why:** bareact-140 run took ~11 min — 57% on sequential 15j regroup despite rule+MiniLM already producing 8 good chapters; 12% on 40× sequential 15b LLM; profile not applied to batch script.
- **Impact:** fast_local path drops ~8+ min and ~50+ structure LLM calls on typical books; quality_cloud still enables 15j with auto_skip when local output sufficient. Tests: extended `test_hierarchy_openai_gate.py` (7).

---

## [2026-06-13] — Phase C: pipeline stage de-scatter assessment + registry reorder

- **What:** Audited the pipeline for the reported "scattered stages / confusing names." Found the substantive de-scatter already complete from the local-ingestion change plan: a single `stage_registry.py` source of truth (log key → `sNN` filename + legacy fallback), clean one-function-per-stage `stages.py`, and a thin registry-driven `runner.py` loop. Ingestion module is small and clearly named (`pdf_extractor`, `text_normalizer`, `ocr_stage`, `layout_enrichment`, `pdf_outline`, `profile`). The only genuinely messy spot — the `STAGE_LOG_FILES` dict was listed out of `sNN` order (s13 before s11/s12, 15-series jumbled) — was reordered to execution order with section comments. **No keys or filenames changed** (fully backward compatible).
- **Why:** A destructive log-key rename would break the legacy-fallback contract relied on by older run folders, scripts, and tests, for cosmetic gain — violating "refactor only when needed" / "do not overbuild". Readability was the real, low-risk win.
- **Impact:** Zero behavior change; registry is easier to read. Full unit suite green (269). Stage map documented in `specs/modules/pipeline-core.md`.

---

## [2026-06-13] — Phase F: deployment (Docker dev/prod + env profiles + storage)

- **What:** Production-grade Docker setup. Backend `Dockerfile` now installs OCR/PDF system deps (tesseract, poppler, libgl), runs as non-root `appuser`, has a `/api/health` `HEALTHCHECK`, and configurable `UVICORN_WORKERS`. Frontend `Dockerfile` is multi-stage: `dev` (Vite) and `prod` (build → nginx static + `/api` reverse proxy with SSE buffering off). New `docker-compose.prod.yml` uses built images, named volumes (`notes_output`, `notes_logs`, `notes_models`, `hf_cache`), `restart: unless-stopped`, and `service_healthy` gating. CORS origins are now env-driven via `AuthSettings.cors_origins` (`FRONTEND_URL` + `CORS_EXTRA_ORIGINS`) instead of hardcoded localhost. Added `.dockerignore` (backend/frontend), `.env.prod.example`, `nginx.conf`, and `specs/deployment.md`.
- **Why:** User requirement — deployment-ready with Docker, local/dev/prod environments, and a defined logging/output storage strategy. Hardcoded localhost CORS and the dev-only frontend container blocked any real deploy.
- **Impact:** `docker compose up` (dev, hot reload) and `docker compose -f docker-compose.prod.yml up -d` (prod, nginx+workers) both work. Persistent data survives redeploys via named volumes. Frontend builds clean; backend app imports + CORS resolve verified.

---

## [2026-06-13] — Phase E: guest mode (anonymous access without OAuth)

- **What:** New `ALLOW_GUEST` setting (`auth/config.py`, default true). `POST /api/auth/guest` now mints an isolated, persisted guest user + short-lived JWT when `AUTH_ENABLED=true` (returns `{user, token}` via new `GuestSessionResponse`); shares the dev identity when auth is off; 403 only when guest is explicitly disabled. `GET /api/auth/config` exposes `allow_guest`. Frontend: `AuthProvider.enterWithoutAuth` stores the guest token, `LoginPage` shows "Continue as guest" alongside OAuth, and exports now download via an authenticated blob fetch (`downloadFile` in `auth/api.ts`) instead of a plain `<a href>` (which could not send the Bearer token).
- **Why:** User requirement — let people use the app without mandatory login, while keeping OAuth available. The old guest path only worked with `AUTH_ENABLED=false` (shared identity, no isolation) and exports 401'd for any token-auth user.
- **Impact:** Anonymous users can upload → run pipeline → chat → export with per-session isolation. Tests: `test_guest_auth.py` (4). Frontend builds clean. `.env.example` documents `ALLOW_GUEST`.

---

## [2026-06-13] — Phase D line-quality: normalizer concern-split + green test suite

- **What:** Resolved an internal contradiction in `markdown_format_normalizer.py` where "Course Outcomes" was both a callout label (kept/formatted) and a syllabus block (stripped) — removed it from `_CALLOUT_LABELS` so syllabus admin is consistently dropped. Realigned stale rewrite/normalizer tests to the current deliberate behavior: syllabus labels dropped, book/paragraph is the default export style (bullet/callout features tested under `NOTES_EXPORT_STYLE=study`), standalone callout labels stripped by postprocess, the missing-section prompt uses the shared section builder, and the consolidation test now exercises backward-page merge-prevention without tripping thin-junk dropping.
- **Why:** The prior session left 7 red tests encoding outdated expectations that conflicted with consistent multi-module policy (drop syllabus admin; book-default). Robustness work (postprocess content-loss guard, title repair) needed a green baseline.
- **Impact:** Full unit suite green (265 passed, up from 249 with 7 failing). No production logic weakened — only the format-then-strip contradiction was removed and stale tests realigned with justification.

---

## [2026-06-13] — LLM cost reduction: rewrite cache + 15j names-pass gate

- **What:** (1) New `src/shared/llm_cache.py` — content-hash disk cache for LLM completions, keyed on model namespace + system + user + max_tokens + version (auto-invalidates on model/prompt change). Wired into the rewrite `_generate` closure via `cached_generate()`. Stored under `output/.llm_cache/` with provenance; toggle with `REWRITE_CACHE_ENABLED` / `LLM_CACHE_DIR`. (2) Stage 15j: added `_hierarchy_titles_need_cloud_cleanup()` gate so `_openai_name_corrections` is skipped when every title is already a clean study label, and moved the cheap local `_refine_semantic_titles` before the LLM names pass to maximize skips.
- **Why:** User priority — reduce LLM API calls/cost and add robustness. Re-running the same PDF previously re-billed every section rewrite; 15j always made a names-correction call even when titles were already clean (it already gated the 3rd polish call but not the 2nd names call).
- **Impact:** Re-runs on unchanged content hit the cache (0 rewrite calls). Well-structured PDFs skip an entire ~4096-token names call. No quality risk: cache is content+model specific; the gate only skips when all titles pass acceptance + are free of partition/prose/generic/noise. Tests: `test_llm_cache.py`, `test_hierarchy_openai_gate.py`.

---

## [2026-06-13] — Subject-agnostic title repair + content-loss guard

- **What:** (1) Added `topic_from_labeled_prose()` in `dropped_heading_registry.py` — extracts a clean topic from labeled body prose (`Section 309: Robbery. — …` → `Robbery`; `Chapter 3: Photosynthesis. — …` → `Photosynthesis`), works across subjects. (2) `is_acceptable_study_title()` now rejects `is_statute_prose_heading`. (3) `pick_section_title()` extracts the topic from statute/labeled prose before other repair and adds statute-prose to `needs_repair`. (4) `fix_verbose_section_titles()` now prefers a clean subheading over raw body-preview prose. (5) `_collapse_generic_disambiguation()` keeps any substantive multi-word non-prose suffix. (6) `notes_body_postprocess.postprocess_rewritten_section()` adds a robustness guard so aggressive filtering never empties a section that had real content.
- **Why:** Bare-act exports leaked statute prose into titles (AC-02/03/04) and produced `Section topic (p.N)` placeholders; postprocess silently emptied short/bullet-only sections (content loss). The title logic was also law-specific; the new extractor generalizes to any subject.
- **Impact:** Cleaner export titles for any PDF subject; no silent body loss. Fixed pre-existing red tests: `test_section_bundler` (sid parse), `test_title_validation` (citation→subheading), `test_heading_cleanup` (generic disambiguation suffix). New tests in `test_heading_title_engine.py`, `test_notes_body_postprocess.py`. **Known pre-existing failures (prior session, not addressed here):** `test_markdown_format_normalizer` (4), `test_missing_section_rewrite`, `test_parallel_rewrite` (config-dependent prompt), `test_section_consolidation` (drop-thin design vs test) — slated for Phase D.

---

## [2026-06-13] — Section-ID anchors in export + audit join fix

- **What:** `document_formatter.chapter_blocks_from_hierarchy` now appends `<!-- sid:SXX -->` to each exported `##`/`###` section heading. Quality `analyzer.build_report` uses `resolve_rewritten_map` (sid-first join) instead of heading-text-only matching. `heading_acceptance.parse_markdown_headings` strips sid tags before AC checks. Tests updated in `test_rewrite_validation.py`, `test_heading_acceptance.py`.
- **Why:** Batch audits reported 22/57 coverage on bare act because display titles in markdown differ from raw hierarchy headings (`Section 309: Robbery. — …` vs cleaned export title). Bodies were present; the join was fragile and subject-agnostic ID mapping was designed but not wired.
- **Impact:** New exports get deterministic section_id → body mapping in quality audit and re-export scripts. DOCX render still strips sid tags (unchanged). Re-run pipeline/export to regenerate MD with sid tags; auditing old MD without tags still falls back to fuzzy heading match.

---

## [2026-06-13] — Full code-reference specs + documentation rule

- **What:** Added `.cursor/rules/13-comprehensive-spec-documentation.mdc`. Created `specs/code-reference/` (pipeline, structure, generation, quality, export, rag, ingestion, interaction, services-scripts) with per-file and per-public-symbol **purpose + why + called-by** tables. Updated `architecture.md`, `overview.md`, `index.md`, `pipeline-core.md`, `llm-generation.md`, `parameters-config.md`, `export-format.md`, module spec links.
- **Why:** User required end-to-end specs documenting every file/function rationale; prior specs were summary-only and stale.
- **Impact:** Agents must update code-reference when changing public symbols. Module specs link to code-reference; avoid duplicating full symbol tables in two places.

---

## [2026-06-13] — Hierarchy enforcement, quality audit, notes body cleanup

- **What:** Added `enforce_chapter_structure()` (15g/15i/15j + rewrite pre-pass): splits mega-chapters, fixes parent mirrors, sanitizes headings, repairs statute prose titles. Added `is_statute_prose_heading()` in `dropped_heading_registry.py`. Added quality module (`heading_acceptance.py`, `line_audit.py`, `heuristics.py`). Added `notes_body_postprocess.py` for post-rewrite cleanup. Wired batch pipeline + audit scoring (readability informational; line quality primary gate). Fixed missing import in `hierarchy_openai_refinement.py`.
- **Why:** Environmental-law syllabus collapsed to 1 chapter after 15j; bare-act exports leaked `Explanation:` / `Section N: … —` as headings; line-audit meta filler and heading-echo issues; specs/tasks were stale vs code.
- **Impact:** Final structuring now runs 15f → 15h → 15i → 15j → 15g with enforce pass at 15g/15i/15j and rewrite. Quality reports include heading AC (AC-01…AC-05, AC-07) and line audit. Tests: `test_enforce_chapter_structure.py`, `test_heading_acceptance.py`, `test_notes_body_postprocess.py`. **Known limitation:** batch re-run pending after import fix; `tasks.md` and module specs updated in this entry.

---

## [2026-06-07] — Full specs sync for paths, stage registry, change plan

- **What:** Updated `architecture.md` (ADR-014/015, repo layout), `pipeline-core.md` (registry helpers, `PipelineResult`, s01–s16 table), `ingestion.md` (single extract web flow), `structure-extraction.md`, `data-models.md`, `overview.md`, `index.md`, `testing.md`, `parameters-config.md`, `logging-debug.md`, `README.md`. Rewrote `ai-agent-workflow/change-plan-local-ingestion.md` and `tasks.md` with completion status.
- **Why:** Specs still referenced old log filenames and `backend/logs`; change plan showed pre-implementation state.
- **Impact:** SDD and agent workflow plan aligned with implemented path/registry work; remaining phases (FLAN, lazy RAG, ingestion.profile) clearly marked pending.

---

## [2026-06-07] — Canonical LOGS_FOLDER, stage file rename (s01–s16), gitignore

- **What:** `LOGS_FOLDER` / `EXPORTS_FOLDER` / `UPLOADS_FOLDER` / `KNOWLEDGE_DB_PATH` in config; `PipelineLogger` writes under `PROJECT_ROOT/logs`. Renamed stage artifacts to `s01_layout_lines.json` … `s16_rag_snapshot.json` with legacy read fallback. Expanded `.gitignore` (backend/logs, backend/output, pdfs, db journals). Code uses `stage_registry.require_artifact` / `resolve_existing_artifact` instead of hardcoded paths.
- **Why:** Logs landed in `backend/logs` while data used repo-root `output/`; stage JSON names were inconsistent (gaps 04–06, mixed 03b/15a).
- **Impact:** Delete `backend/logs` and `backend/output` safely; new runs use `{PROJECT_ROOT}/logs/run_*/s*.json`. Old run folders still readable via legacy fallback.

---

## [2026-06-07] — Pipeline registry, dead-code cleanup, single PDF extract

- **What:** Added `pipeline/stage_registry.py`; renamed 15b log keys to `15b_doubted_resolved` / `15b_revalidation`; removed legacy log whitelist slots and dead methods (`record_decision`, `gate_toc_candidates`, `HeadingGateTraceRecord`, RAG wrappers). Fixed double `extract_pdf` in `ingestion_service` and `command_loop`; extended `PipelineResult` with `lines`, `book_title`, `total_pages`. Fixed `export_handler.py` import typo. Tests: `test_stage_registry.py`, `test_pipeline_single_extract.py`.
- **Why:** Scattered naming, unused code, and duplicate PDF extraction slowed uploads and confused debugging.
- **Impact:** One registry for stage artifacts; upload/CLI ingest call `extract_pdf` once; CLI export handler importable again.

---

## [2026-06-07] — Local ingestion master change plan (agent workflow)

- **What:** Added `ai-agent-workflow/change-plan-local-ingestion.md` — full phased plan: double-extract fix, `ingestion.profile`, BigBird 15b/15e, FLAN-T5-base per-title 15f, lazy RAG, rerank/context phases, STAGE_REGISTRY cleanup. Updated `tasks.md` Stage 6, `SDD.md`, `index.md` §7.
- **Why:** Consolidate performance, local-model, and structure-quality decisions from design discussion.
- **Impact:** Implementation order and acceptance criteria documented; specs to update per phase before code.

---

## [2026-06-07] — Move ingestion/RAG strategy to ai-agent-workflow

- **What:** Moved `ingestion-toc-rag-strategy.md` from `specs/` to `ai-agent-workflow/`. Added `ai-agent-workflow/.gitignore` for local agent scratch. Updated `specs/index.md` and `ai-agent-workflow/SDD.md` links.
- **Why:** Strategy analysis is agent workflow material, not authoritative SDD.
- **Impact:** `specs/` holds only committed design specs; TOC/RAG roadmap lives under `ai-agent-workflow/`.

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

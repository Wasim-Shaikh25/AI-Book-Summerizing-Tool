# Code Reference — Pipeline

> **Package:** `backend/src/modules/pipeline/`  
> **Module spec:** [../modules/pipeline-core.md](../modules/pipeline-core.md)

---

## Files

| File | Purpose | Why separate file |
|------|---------|-------------------|
| `runner.py` | Execute ordered stage list, optional DB persist | Thin shell — no business rules (ADR-008) |
| `context.py` | `PipelineContext` mutable state bag | Stages share state without globals |
| `stages.py` | One function per pipeline stage plugin | Plugin architecture for testability |
| `stage_registry.py` | Log key → artifact filename map | Single source of truth (ADR-015); legacy read fallback |
| `stage_catalog.py` | Semantic log keys, display names, legacy aliases | Human-readable naming; on-disk filenames unchanged |
| `stage_15b.py` | Wire doubted-section resolver into pipeline | Resolver logic in structure/; hook in pipeline |
| `llm_chat_client.py` | Unified OpenAI/OpenRouter client | Shared by resolve_doubted_toc, group_chapters, clean_titles, cloud_hierarchy, rewrite, Q&A |
| `openrouter_adapter.py` | OpenRouter HTTP adapter | Provider-specific code isolated from client |
| `__init__.py` | Re-export `run_pipeline` | Stable import path |

---

## `runner.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run_pipeline(pdf_path, *, enable_logs, persist_to_db)` | Run all stages, return `PipelineResult` + logger | Production entry for CLI, web ingest, scripts | `IngestionService`, `run_full_openai_pipeline.py`, debug trace |
| `_persist(ctx)` | Write headings/fragments to SQLite | Optional persistence after structure complete | `run_pipeline` when `persist_to_db=True` |

---

## `context.py` — `PipelineContext`

| Field | Purpose | Why |
|-------|---------|-----|
| `pdf_path` | Source PDF | Provenance for logs and DB |
| `lines` | `list[NormalizedLine]` | Single extract result — avoid double `extract_pdf` |
| `book_title` | Title from metadata or filename | Cover, DB, export |
| `final_headings`, `fragments` | Structure outputs | TOC persistence, rewrite |
| `dropped_registry` | `DroppedHeadingRegistry` | Rejected headings must not reappear as titles |
| `logger` | `PipelineLogger` | Stage JSON artifacts under `logs/run_*/` |
| `on_progress` | Callback `(stage_id, message)` | Web upload progress UI |

---

## `stages.py` — stage functions (semantic names)

Deprecated aliases (`stage_extract`, `stage_noise`, …) remain at file bottom.

| Symbol | Log artifact(s) | Purpose | Why | Called by |
|--------|-----------------|---------|-----|-----------|
| `stage_ingest_pdf` | — | `extract_pdf` once | Fixes double-extract performance bug | `runner.py` |
| `stage_log_layout` | `s01`, `s11` | Layout lines + visual elements | Debug PDF annotation | `runner.py` |
| `stage_filter_noise` | `s02` | Mark header/footer noise | Heading candidates must ignore page chrome | `runner.py` |
| `stage_score_heading_candidates` | `s03` | Score heading candidates | Deterministic heading detection | `runner.py` |
| `stage_gate_heading_candidates` | `s04` | Validity gate (paragraph-like, embeddings) | Block false headings | `runner.py` |
| `stage_filter_continuity` | `s06` | Continuity filter | Headings must align with line flow | `runner.py` |
| `stage_build_fragments` | `s05` | Build fragments between headings | Section bodies for rewrite/RAG | `runner.py` |
| `stage_clean_toc` | — | Strip TOC-flagged candidates | TOC rows are not content sections | `runner.py` |
| `stage_detect_toc` | (in finalize) | Repeat-detection TOC + document-wide contents-page detection (`contents_region.detect_contents_regions`, gated by `CONTENTS_REGION_DETECTION`) unioned into `toc_section_line_ids` | Late TOC books + mid-document index pages need special handling | `runner.py` |
| `stage_flag_doubted_toc` | `s12` | Flag doubted segments when `first_toc_page > 3` | Syllabus/admin pages confuse structure | `runner.py` |
| `stage_resolve_doubted_toc` | `s15b_*` | Run doubted resolver + revalidation | Recover real headings after late TOC | `runner.py` |
| `stage_finalize_heading_list` | `s07`–`s10` | Final heading set + metadata | Consumer-facing heading list | `runner.py` |
| `stage_validate_early_titles` | `s13` (if enabled) | Deterministic title validation pass | Catch citation fragments before structure | `runner.py` |
| `stage_compute_document_profile` | `s00_document_profile.json` | Measured document shape + tuning knobs | Subject-agnostic thresholds for structure/rewrite | `runner.py` |
| `stage_build_book_structure` | `s15a`–`s16` files | Delegate to `run_structure_phases` | Chapter tree for rewrite/export | `runner.py` |

**Human-readable map:** [../modules/stage-catalog.md](../modules/stage-catalog.md)

---

## `stage_catalog.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `StageSpec` | One pipeline step metadata | Links semantic ID to log contract | Docs, tests |
| `PIPELINE_STAGES` | 14 top-level steps | Readable stage inventory | `stage-catalog.md` spec |
| `STRUCTURE_PHASES` | 10 structure sub-steps | Semantic log keys for structure | `structure_orchestrator.py` |
| `STRUCTURE_LOGICAL_GROUPS` | partition / chapters / titles / publish | Explains consolidation groups | Docs, progress |
| `LOG_KEY_TO_SEMANTIC` | log_key → semantic_id | Readers and audit tools | `semantic_stage_id()` |
| `LEGACY_LOG_KEY_ALIASES` | `15e_*` → semantic key | Old run folders + scripts | `normalize_log_key()` |
| `normalize_log_key(key)` | Resolve legacy numeric log key | Backward compatibility | `stage_registry` resolvers |
| `LEGACY_FN_ALIASES` | old `stage_*` → new fn name | Backward-compatible imports | `stage_progress_for()` |

---

## `stage_registry.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `STAGE_LOG_FILES` | Dict log_key → `sNN_*.json` | Whitelist prevents random log files | `PipelineLogger`, scripts |
| `get_pipeline_stages()` | Ordered stage callables | Registry drives runner | `runner.py` |
| `stage_progress_for(id)` | Human progress message; accepts legacy fn names | Upload UI | `ingestion_service` |
| `semantic_stage_id(log_key)` | Log key → semantic ID | Audit reports, docs | Quality audit, scripts |
| `artifact_path(log_dir, key, for_write)` | Canonical write path | Always write new canonical names | Scripts rerunning stages |
| `resolve_existing_artifact(log_dir, key)` | Read canonical or legacy path | Old runs still readable | Rewrite, audit, export scripts |
| `resolve_chapter_hierarchy_artifact(log_dir)` | Prefer cloud → refine → place → clean → validate → group | Latest refined hierarchy wins | `toc_sections.py`, quality audit |
| `require_artifact(log_dir, key)` | Fail fast if missing; accepts legacy keys | Scripts need explicit errors | Export, rewrite scripts |
| `STAGE_PARTITION_SECTIONS`, `STAGE_GROUP_CHAPTERS`, … | Semantic log key constants | Avoid string typos | Tests, services |
| `STAGE_15D` … `STAGE_15J` | **Deprecated** aliases | Backward-compatible imports | Legacy scripts |

---

## `stage_15b.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run_stage_15b_if_doubted(...)` | Run resolver when book is doubted | Only pay LLM cost when late TOC detected | `stage_resolve_doubted_toc` |
| `lines_to_resolver_dicts(lines)` | Adapter to resolver input shape | Resolver expects plain dicts | `run_stage_15b_if_doubted` |
| `apply_resolution_to_headings(headings, resolution)` | Merge resolver output into headings | Pipeline uses `FinalHeading` list | `run_stage_15b_if_doubted` |

---

## `llm_chat_client.py` — `LlmChatClient`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `from_config()` | Build client from env | Central provider selection | Stages, rewrite, Q&A |
| `chat(messages, **kwargs)` | Chat completion | Single API for all LLM calls | structure + rewrite stages |
| `chat_with_provider(provider, ...)` | Force specific provider | Fallback order in rewrite router | `RewriteModelRouter` |
| `chat_enabled()` | Whether any provider configured | Skip LLM stages gracefully | Structure stages |
| `last_model_label()` | Provenance string | Logging and audit | Pipeline logs |

---

## `openrouter_adapter.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `chat_openrouter(messages, ...)` | OpenRouter completions HTTP | OpenRouter differs from OpenAI SDK | `LlmChatClient` |
| `openrouter_model_candidates()` | Model list from env | Free-tier model rotation | Client init |

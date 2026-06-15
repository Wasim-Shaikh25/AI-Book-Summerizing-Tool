# Code Reference — Generation

> **Package:** `backend/src/modules/generation/`  
> **Module spec:** [../modules/llm-generation.md](../modules/llm-generation.md)

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `rewrite.py` | `RewriteEngine` — full book rewrite to MD/DOCX | Main rewrite orchestrator |
| `parallel_rewrite.py` | Parallel/sequential section LLM jobs | Speed for 50+ sections |
| `rewrite_prompts.py` | System/user prompts, profiles, normalization | Central prompt policy — book mode prose rules |
| `notes_body_postprocess.py` | Strip meta filler, heading echo, thin bullets | Line-audit failures without re-prompting entire book |
| `notes_structure_fix.py` | Post-rewrite MD structural cleanup (headings, dedupe, low-grounding) | Fix structural defects without editing body prose; standalone-runnable |
| `markdown_format_normalizer.py` | Strict MD normalization | Prevent pseudo-bullet paragraphs |
| `rewrite_validation.py` | Coverage validation, rewritten_map I/O | Ensure every section has body |
| `toc_sections.py` | Load 15d/15e/15j hierarchy artifacts | Rewrite reads latest stage logs |
| `section_bundler.py` | Group sections into rewrite bundles | Token efficiency when bundling enabled |
| `bundled_rewrite.py` | Multi-section per LLM call | Fewer API calls for small sections |
| `missing_section_rewrite.py` | Auto-retry missing sections | Coverage gaps after parallel race/timeouts |
| `model_router.py` | Provider fallback order | Resilience when OpenAI rate-limits |
| `qa_engine.py` | Book Q&A with RAG | Chat/CLI ask handler |

---

## `rewrite.py` — `RewriteEngine`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run(user_instruction, export_to_word, ...)` | Full rewrite pipeline | CLI, web, `run_full_openai_pipeline.py` | Handlers, scripts |
| `rewrite_sections(sections, instruction, ...)` | Rewrite section list | Testable core without I/O | `run` |

**Rewrite load order (why):** `resolve_chapter_hierarchy_artifact` prefers **15j → 15i → 15h → 15f → 15g → 15e** so rewrite uses latest refined hierarchy.

**Pre-rewrite:** `enforce_chapter_structure(chapter_hierarchy)` — 15j collapse and mirrors fixed before section jobs start.

---

## `notes_structure_fix.py` — post-rewrite structural cleanup

Runs **after** export. Edits only headings/structure — never section body prose. Detection is subject-agnostic (structural `classify_heading` + embedding similarity + measured grounding). The TOC is regenerated from repaired headings.

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `fix_notes_markdown(md_text, *, engine, chat, source_by_id, merge_duplicates_apply, drop_low_grounding)` | Orchestrator → `(new_md, FixReport)` | Single entry for all structural fixes | `structure_fix_runner.run_structure_fix`, `scripts/fix_notes_structure.py` |
| `parse_notes_md(md_text)` → `NotesDoc` | Split preamble / TOC tail / chapters→sections | Lossless model for safe re-emit | `fix_notes_markdown`, tests |
| `render_notes_md(doc)` | Re-emit MD; regenerate TOC from headings | Keep TOC consistent with repaired titles | `fix_notes_markdown` |
| `repair_headings(doc, report, *, chat)` | Replace noisy `#`/`##`/`###` titles | Titles failing `classify_heading` fail AC-03/AC-04 | `fix_notes_markdown` |
| `merge_duplicates(doc, report, *, apply_merge, sim_threshold)` | Flag/opt-in merge adjacent near-identical sections | Removes repeated topics; merge gated (false-positive risk) | `fix_notes_markdown` |
| `flag_low_grounding(doc, report, source_by_id, *, drop)` | Flag/opt-in drop index/contents-style sections | Ungrounded bodies (source was a title list) | `fix_notes_markdown` |
| `FixReport` / `FixChange` | Provenance: engine, models, before→after | Audit trail of every structural edit | Script writes `<stem>.structure_fix.json` |

**Engine (hybrid):** one batched LLM call (`_llm_titles`) maps id→clean title when chat is enabled; offline falls back to MiniLM-from-body (`_offline_title_from_body` via `mini_lm_encoder`) then `ensure_study_safe_heading`. A repaired title is only applied if it classifies `looks_ok`.

## `structure_fix_runner.py` — pipeline wiring

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `structure_fix_enabled()` | `NOTES_STRUCTURE_FIX_ENABLED` | Gate automatic step in full pipeline | `run_full_openai_pipeline.py` |
| `run_structure_fix(md_text, *, log_dir, engine, ...)` | Load source from logs + call `fix_notes_markdown` | Single integration point for pipeline and CLI | `run_full_openai_pipeline.py`, `fix_notes_structure.py` |
| `build_source_by_id_from_log_dir(log_dir)` | Reconstruct section source spans | Low-grounding flag/drop needs pipeline artifacts | `run_structure_fix` |
| `write_structure_fix_report(report, path)` | Persist JSON provenance | `<stem>.structure_fix.json` beside output MD | Pipeline + CLI |
| `propagate_titles_to_hierarchy(fixed_md, hierarchy, *, hierarchy_path=None)` | Sync final Markdown section/chapter titles into the in-memory hierarchy (DOCX) and rewrite the on-disk hierarchy artifact (audit AC-04) | DOCX renders raw `hierarchy['heading']` and the audit reads the on-disk artifact — both bypass the cleaned Markdown, so repaired/display-resolved titles never reach them and `heading_acceptance`/`pdf_match` stay WARN | `run_full_openai_pipeline.py` |
| `_build_title_maps(fixed_md)` | Parse final MD → `(section_title_by_sid, chapter_title_by_sid, chapter_titles_in_order)` | Markdown is the single source of truth for titles | `propagate_titles_to_hierarchy` |
| `_apply_titles_to_hierarchy(hierarchy, ...)` | Patch a hierarchy dict in place: sections by `section_id`, chapters by sid-majority vote (positional fallback only when no sids) | Robust to refine-stage reordering between in-memory and on-disk hierarchies | `propagate_titles_to_hierarchy` |

---

## `parallel_rewrite.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_rewrite_jobs(sections, overlap)` | One job per section + context overlap | Adjacent context reduces boundary gaps | `rewrite_sections_parallel` |
| `resolve_parallel_workers()` | `REWRITE_PARALLEL_WORKERS` | Throughput vs rate limits | `rewrite_sections_parallel` |
| `resolve_context_overlap_chars()` | Overlap from env | Section N sees tail of N-1 | Job builder |
| `rewrite_sections_parallel(jobs, router, ...)` | Thread pool LLM calls | 4 workers default for medium books | `RewriteEngine` |

---

## `rewrite_prompts.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_dynamic_rewrite_system_prompt(profile, ...)` | System prompt with guardrails | Anti-meta, book-mode prose, simple English ≠ short sentences | Parallel rewrite |
| `resolve_rewrite_profile(notes_style, depth)` | `RewriteProfile` from config + user | Exam vs book vs compact modes | `RewriteEngine` |
| `build_section_user_prompt(section, instruction)` | Per-section user message | Source preview + user ask | Job builder |
| `normalize_rewritten_section(body, section, profile)` | Post-LLM normalize | Calls `postprocess_rewritten_section` + MD normalizer | After each LLM response |
| `user_prefers_paragraphs(profile)` | Book mode → continuous prose | User rejected bullet-like paragraphs | Prompt + normalizer |
| `infer_content_depth(instruction)` | Map user ask to depth | Token budget hint | Profile resolution |

**Prompt guardrails (why added):**

| Rule | Why |
|------|-----|
| No "This chapter covers…" | Line-audit meta filler FAIL |
| No heading echo in body | Export adds `##`; body must not repeat |
| Book mode = prose paragraphs | Pseudo-bullets failed line audit and readability |
| Bullets only for enumerations/examples | Lists are OK; whole section as bullets is not |
| Simple English ≠ short sentences | User rejected AC-06 sentence-length gate |

---

## `notes_body_postprocess.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `postprocess_rewritten_section(body, section_heading, profile)` | Deterministic body cleanup | Cheaper than re-LLM; fixes systematic template leaks | `normalize_rewritten_section` |

**Strips:** meta filler lines, heading echo, syllabus/admin phrases, thin one-line bullets, standalone `**bold**` fake subheadings.

---

## `markdown_format_normalizer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `strict_normalize_markdown(text, prefer_paragraphs)` | Enforce MD shape | LLM outputs inconsistent spacing/bullets | `normalize_rewritten_section` |
| `prefer_paragraph_format(profile)` | Book mode flag | Disables artificial paragraph splitting | Normalizer |
| `split_runon_bullets(text)` | Fix run-on bullet lines | OCR-style single-line lists | Normalizer |

**Why `_split_long_paragraph` disabled:** Artificial breaks created bullet-like multi-line paragraphs that failed line audit.

---

## `rewrite_validation.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `validate_rewrite_coverage(sections, rewritten_map)` | Compare hierarchy vs map keys | Missing section = incomplete notes | After rewrite |
| `save_rewritten_map` / `load_rewritten_map` | Persist section bodies | Re-export DOCX without re-LLM | Export scripts |
| `heading_similarity(a, b)` | Detect duplicate section titles | Quality + dedup |
| `strip_redundant_section_heading(body, title)` | Remove echoed `##` from body | Export adds heading separately |

---

## `toc_sections.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `load_rewrite_sections(log_dir, ...)` | Sections for rewrite from latest artifacts | Single loader for CLI/web/scripts | `RewriteEngine`, `BookQaEngine` |
| `load_chapter_hierarchy_json(path)` | Parse hierarchy JSON; accepts both `{items:{chapters}}` (s15f) and top-level `{chapters}` (s15j) schemas | Loader must not depend on which optional stage produced the artifact | `load_rewrite_sections`, `run_full_openai_pipeline.py`, tests |
| `find_latest_hierarchy_log(log_dir)` | Resolve 15j→15e chain | Scripts without full pipeline | `rewrite_missing_sections.py` |
| `load_chapter_tree(hierarchy)` | Nested chapter/section tree | Export formatter | DOCX export |

---

## `section_bundler.py` / `bundled_rewrite.py`

| Symbol | Purpose | Why |
|--------|---------|-----|
| `build_rewrite_bundles(sections, bundle_size)` | Group small adjacent sections | One LLM call for thin sections |
| `resolve_bundle_size()` | Env `REWRITE_BUNDLE_SIZE` | Default 1 section/call for quality |
| `rewrite_bundles_parallel(bundles, ...)` | Parallel bundle jobs | Same worker pool as sections |

---

## `missing_section_rewrite.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `retry_missing_sections(...)` | Re-run LLM for gaps | Parallel failures / token limits | `RewriteEngine` after first pass |
| `auto_retry_missing_enabled()` | `REWRITE_AUTO_RETRY_MISSING` | Can disable for debug | `RewriteEngine` |

---

## `model_router.py` — `RewriteModelRouter`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `generate(messages, **kwargs)` | Try providers in `REWRITE_PROVIDER_ORDER` | OpenRouter/OpenAI fallback | Rewrite, Q&A |

---

## `qa_engine.py` — `BookQaEngine`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `answer(question, book_id, sections)` | RAG + LLM answer | Web/CLI Q&A | `AskHandler`, `ChatService` |
| `retrieve_sections(question, sections)` | Lexical fallback when RAG off | `UPLOAD_SKIP_RAG` default | `answer` |
| `check_subject_relevance(question, sections)` | Block off-topic questions | Prevent hallucination outside book | `answer` |

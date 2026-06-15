# Code Reference — Structure

> **Package:** `backend/src/modules/structure/`  
> **Module spec:** [../modules/structure-extraction.md](../modules/structure-extraction.md)

---

## Top-level files

| File | Purpose | Why |
|------|---------|-----|
| `noise_filter.py` | Mark header/footer/page-number lines | Page chrome scores as false headings |
| `candidate_scoring.py` | Score lines as heading candidates | Deterministic first pass before LLM |
| `heading_validity_gate.py` | Gate invalid candidates (paragraph-like, embeddings) | Block list items and body text as headings |
| `continuity_filter.py` | Require heading line continuity | Headings must sit on plausible layout lines |
| `fragments.py` | Build text fragments between headings | Section bodies for rewrite and RAG |
| `toc_cleaning.py` | Remove TOC-flagged lines from candidates | TOC is navigation, not content |
| `toc_repeat_detection.py` | Detect repeated heading patterns = TOC | Late syllabus books have admin TOC pages |
| `contents_region.py` | Detect mid-document index/contents pages (enumeration-dominated) | Per-chapter index pages slip past the repeated-heading detector and become ungrounded sections |
| `heading_heuristics.py` | Force-invalid enumerated list items | "a) First point" is not a section title |
| `heading_title_validation.py` | Stage s13 deterministic title rules | Catch citation fragments before hierarchy build |
| `context_preview_builder.py` | Short body preview around line index | LLM/resolver context without full section |
| `dropped_heading_registry.py` | Central pattern registry for rejected titles | **Pattern-based, not per-book** — one rule set for all PDFs |
| `section_consolidation.py` | Merge low-value adjacent sections | Reduce noise before chapter build |

---

## `dropped_heading_registry.py` (critical)

| Symbol | Purpose | Why |
|--------|---------|-----|
| `DroppedHeadingRegistry` | Track dropped heading texts/ids | Prevent same bad title re-entering via LLM |
| `is_structural_partition_heading(text)` | `CHAPTER I:`, `PART II`, `MODULE N` | Partitions are chapter breaks, not section titles |
| `is_statute_prose_heading(text)` | `Explanation:`, `Section 309: … —` | Bare-act statute lines are prose, not study headings |
| `is_incomplete_pdf_heading(text)` | Currency tails, page footers | PDF extraction artifacts |
| `is_noisy_fragment_heading(text)` | Classification rows, bare markers | OCR/layout noise |
| `is_syllabus_heading(text)` | Syllabus/admin labels | Not teachable legal topics |
| `is_acceptable_study_title(text)` | Positive check for export | AC-04 display resolver |
| `partition_heading_to_study_title(text)` | Convert partition to short label | When partition must become chapter title |
| `load_dropped_registry_from_log_dir(log_dir)` | Restore registry from prior run | Stage reruns stay consistent |

---

## `final_structuring/structure_orchestrator.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `phase_partition(...)` | 15a + 15d | Build tree and rewrite sections | `run_structure_phases` |
| `phase_chapters(...)` | 15e + 15h | Group and place chapters | `run_structure_phases` |
| `phase_titles(...)` | 15f + 15i + 15j | Clean, refine, optional cloud polish | `run_structure_phases` |
| `phase_publish(...)` | 15g + 15c + 16 | Validate, assemble book, RAG snapshot | `run_structure_phases` |
| `run_structure_phases(...)` | Run all four phases; write legacy JSON artifacts | Consolidated orchestration without removing sub-steps | `run_final_structuring_stage` |

---

## `final_structuring/final_structuring_stage.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run_final_structuring_stage(...)` | Thin delegate to `run_structure_phases` | Stable import for pipeline stage | `stage_build_book_structure` |

---

## `book_assembler.py`

| Symbol | Stage | Purpose | Why |
|--------|-------|---------|-----|
| `build_heading_hierarchy(headings, lines)` | 15a | Tree from flat headings | Parent/child for ultimate sections |
| `build_ultimate_sections(...)` | 15d | Sections with source previews | Rewrite unit — one section = one rewrite job. **Grounding gate**: skips rows whose reconstructed body is an index/contents listing (`text_grounding.is_contents_listing`) when `PARTITION_DROP_LOW_GROUNDING` is on; count in `meta.low_grounding_dropped` |
| `assemble_final_book(...)` | 15c | Final book JSON for DB/export | Combines hierarchy + metadata |
| `build_rag_snapshot(...)` | 16 | Section list for RAG indexing | Lazy RAG reads this artifact |

---

## `contents_region.py`

| Symbol | Purpose | Why |
|--------|---------|-----|
| `detect_contents_regions(lines, *, min_enum_lines=5, enum_ratio=0.5)` | Return `(line_ids, log)` for pages whose non-noise lines are enumeration-dominated | Mid-document per-chapter index/contents pages otherwise become noisy, ungrounded sections. **Called by** `stage_detect_toc` (unions ids into `toc_section_line_ids`). Subject-agnostic — uses `text_grounding.is_enumerated_title_line` only |

Shared grounding primitives live in `src/shared/text_grounding.py` (`ENUM_TITLE_LINE_RE`, `is_enumerated_title_line`, `real_content_chars`, `enumerated_line_ratio`, `is_low_grounding`, `is_contents_listing`); `generation/rewrite_fidelity.py` delegates to it.

---

## `chapter_hierarchy_builder.py` — Stage 15e

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_chapter_hierarchy(ultimate, hierarchy, max_sections)` | Group 15d sections into chapters | Exam notes need chapter outline | `run_final_structuring_stage` |

**Why:** Flat 15d sections are too granular for export TOC; chapters group by legal theme.

---

## `heading_cleanup.py` — Stage 15f

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `clean_heading_hierarchy(hierarchy, ultimate, registry)` | Main 15f entry | Weak titles from PDF need cleanup | `run_final_structuring_stage` |
| `sanitize_hierarchy_headings(hierarchy)` | Strip `(p. NNN)`, normalize whitespace | Page refs are not part of study titles | `enforce_chapter_structure`, 15f |
| `merge_duplicate_named_chapters(chapters)` | Dedup identical chapter names | LLM/TOC duplicates confuse export |
| `disambiguate_duplicate_section_headings(chapters)` | Add suffix when sections collide | Export MD needs unique `##` titles |
| `canonical_heading_for_match(text)` | Normalize for comparison | Duplicate detection |

---

## `chapter_placement.py` — Stage 15h

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run_chapter_placement(hierarchy)` | 15h entry: splits, reassignment, rename | Initial chapter boundaries before refinement | `run_final_structuring_stage` |
| `is_structural_chapter_break(title)` | Detect MODULE/UNIT/PART | Syllabus books have explicit part boundaries |
| `split_chapters_at_structural_markers(chapters)` | Split at structural titles | One mega-chapter spans unrelated units |
| `split_oversized_chapters(chapters)` | Split when section count > max | 15e/15j can leave 20+ sections in one chapter |
| `reassign_outlier_sections(chapters)` | Move sections by page cohesion | Mis-grouped sections by page order |
| `refine_broad_chapter_titles(chapters)` | Replace generic chapter names | "Overview of…" is not a study chapter |
| `enforce_chapter_structure(hierarchy)` | **Final safety net** | 15j regroup collapses syllabus to 1 chapter; mirrors and statute prose leak | 15g, 15i, 15j, `RewriteEngine` |
| `universal_clean_heading(text)` | Rule-based title cleanup | Shared cleanup before display |

**`enforce_chapter_structure` steps (why each):**

1. Split at structural markers — syllabus MODULE boundaries
2. Split oversized chapters — environmental law had 22 sections in 1 chapter
3. `fix_parent_mirror_chapters` — chapter title copied from first section
4. `sanitize_hierarchy_headings` — strip page tails
5. `fix_verbose_section_titles` / `fix_unacceptable_section_titles` — prose/statute titles
6. Re-split oversized after fixes — fixes can re-merge sections
7. Renumber chapters — stable `chapter_id` order

---

## `subheading_refinement.py` — Stage 15i

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run_heading_refinement(hierarchy)` | 15i entry | Polish titles before 15j OpenAI pass | `run_final_structuring_stage` |
| `fix_parent_mirror_chapters(hierarchy)` | Chapter ≈ first section | Constitutional/env law had mirror chapters | `enforce_chapter_structure` |
| `fix_verbose_section_titles(hierarchy)` | Shorten essay-length titles | PDF headings are often full sentences |
| `fix_unacceptable_section_titles(hierarchy)` | Reject statute/syllabus/noise titles | Same rules as `dropped_heading_registry` |
| `fix_placeholder_section_titles(hierarchy)` | Replace "Section topic" placeholders | LLM placeholder labels |
| `refine_chapter_titles(hierarchy)` | Context-based chapter names | Generic names from 15e |
| `refine_section_headings_from_context(hierarchy)` | Use source preview for title | Weak PDF heading → better study label |
| `refine_subheadings_in_hierarchy(hierarchy)` | Optional `###` labels | Subtopic structure for long sections |

---

## `hierarchy_openai_refinement.py` — Stage 15j

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `run_hierarchy_openai_refinement(hierarchy)` | OpenAI regroup + rename + polish | Thematic chapters for exam notes; fixes weak 15e groupings | `run_final_structuring_stage` |

**Why:** Rule-based 15e cannot always infer legal themes across 50+ syllabus sections; LLM groups consecutive related sections.

**Side effect:** Can over-merge into one chapter → **`enforce_chapter_structure` required after 15j**.

---

## `title_validation.py` — Stage 15g

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `validate_chapter_hierarchy(hierarchy, ultimate, registry)` | FLAN/MiniLM title safety net | Last check before final book; catches awkward LLM titles | `run_final_structuring_stage` |

Runs **after** 15j so validation sees final regrouped tree.

---

## `hierarchy_export.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `hierarchy_already_refined(hierarchy)` | Skip re-run if meta says refined | Avoid double OpenAI cost on re-export | Export scripts |
| `refine_hierarchy_for_export(hierarchy, log_dir)` | Apply 15h→15i→15j if needed | Old logs may lack 15j | `reexport_docx.py` |

---

## `heading_title_engine.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `resolve_section_display_heading(section)` | Export-facing section title | Internal heading may differ from study label | Export, AC-04 |
| `resolve_chapter_display_heading(chapter)` | Export-facing chapter title | Strip partitions, apply study case | Export |
| `pick_section_title(section, preview)` | Choose best title from candidates | Weak PDF title + good preview |
| `title_from_fragment_preview(preview)` | Derive title from body start | When heading is empty/noise |

---

## `chapter_cohesion.py` / `chapter_merger.py`

| Symbol | Purpose | Why |
|--------|---------|-----|
| `consolidate_chapter_hierarchy(hierarchy)` | Merge related adjacent chapters | 15j can over-split thin chapters |
| `merge_undersized_chapters(chapters)` | Combine chapters with too few sections | Avoid 1-section chapters except MODULE breaks |
| `chapters_are_related(a, b)` | MiniLM + heading overlap | Thematic cohesion without hardcoded book rules |

---

## Stage 15b files

| File | Symbol | Purpose | Why |
|------|--------|---------|-----|
| `doubted_section_resolver.py` | `resolve_doubted_section` | Classify doubted lines | Late TOC pages look like headings |
| `revalidation.py` | `revalidate_selected_candidates` | LLM second pass on flagged segments | Reduce false negatives |
| `signal_extractor.py` | `compute_line_signals` | Deterministic features | Resolver input before LLM |
| `models/segment_llm_classifier.py` | `FastSegmentLlm` | Fast local classifier | `fast_local` ingestion profile |
| `models/mini_lm_encoder.py` | `get_mini_lm_encoder` | Embedding similarity | Title pick, cohesion |
| `models/cross_encoder_model.py` | `get_cross_encoder` | Heading/body coherence score | 15b revalidation |
| `models/mini_lm_title_pick.py` | `mini_lm_pick_title` | Pick best title from candidates | 15f/15i when rules ambiguous |
| `models/flan_title_cleaner.py` | FLAN-T5 title cleanup | Local model title rewrite | `fast_local` without cloud LLM |
| `models/flan_title_validator.py` | FLAN validation pass | 15g local validation path |

---

## `logging/pipeline_logger.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `PipelineLogger.create(pdf_file, enabled)` | Create run dir under `LOGS_FOLDER` | Reproducible stage artifacts | `run_pipeline` |
| `write_stage(name, payload)` | Write whitelisted stage JSON | Debug and rewrite reload | All stages |
| `write_stage_payload(filename, payload)` | Write by explicit filename | 15d/15e use custom keys | `final_structuring_stage` |
| `NoOpPipelineLogger` | Zero-cost logger | Production when logs disabled | `run_pipeline` |

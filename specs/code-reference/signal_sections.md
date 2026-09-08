# Code Reference — Signal-Sections Pipeline V2

> **Packages:**
> - `backend/src/modules/structure/signal_sections/`
> - `backend/src/modules/generation/signal_rewrite/`
> - `backend/src/modules/export/signal_export/`
> **Module spec:** [../modules/pipeline-signal-sections.md](../modules/pipeline-signal-sections.md)
> **Status:** Implemented (2026-06-16) — opt-in V2 pipeline.

This is the **exhaustive** symbol inventory for the signal-sections pipeline (rule 13). All entries below are **net-new files**; no existing modules were modified.

---

## 1. `backend/src/modules/structure/signal_sections/`

### File: `__init__.py`
- **Purpose:** Package marker + public module list.
- **Why:** Group all PDF-mirror structure helpers so the legacy `structure/final_structuring/` chain is never imported.

### File: `signal_classifier.py`

- **One-line purpose:** Pick the high-signal heading line ids that will become section boundaries.
- **Why this file exists:** The legacy pipeline turns *every* high-probability heading into its own section, then mutates the result with several LLM passes. The signal pipeline needs a deterministic, percentile + structural-marker pick to keep section count proportional to the PDF's own headings and to avoid LLM-driven boundary drift.

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `BoundaryHeading` (dataclass) | Frozen record: `line_id, text, page_number, score, source, signals` | Carries the picked boundary through partitioning + logging | `signal_partitioner`, `signal_logger`, runner |
| `BoundarySelectionStats` (dataclass) | Stats: validated count, structural count, percentile count, threshold used | Persisted for audit so reruns are explainable | `signal_logger`, runner |
| `is_structural_marker(text)` → bool | True for `CHAPTER N`, `MODULE N`, `UNIT N`, `PART N`, Roman major (`II. Topic`), and `(Arts. N…)` ranges ≥ 20 chars | Universal partition rules with no subject names; reused by `pdf_chapter_grouper` to find chapter starts | `pick_boundary_line_ids`, `pdf_chapter_grouper.find_chapter_marker_line_ids` |
| `pick_boundary_line_ids(...)` → `(List[BoundaryHeading], BoundarySelectionStats)` | Combine structural markers (always kept when `include_structural`) with the top `percentile` % of validated headings that also clear `min_score` | The user's "very high-signal → next very high-signal" rule expressed deterministically | `pipeline_signal_sections.run_signal_pipeline` |

Private helpers (`_score_map_from_scoring_log`, `_percentile_threshold`) are documented only because they encode the non-obvious "score from `s03_candidate_scoring.json`" mapping. No external callers.

### File: `signal_partitioner.py`

- **One-line purpose:** Turn picked boundaries into sections that span boundary → next boundary, with non-boundary validated headings preserved as inner-heading metadata.
- **Why this file exists:** This is the architectural opposite of `book_assembler.build_ultimate_sections` — instead of one section per probable heading, one section per *high-signal* heading. Lower-confidence headings inside the span survive as hints for the LLM rather than being dropped or promoted.

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `PartitionedSection` (dataclass) | `section_id, heading (verbatim), page_number, line_id_start, line_id_end, body, body_chars, inner_headings` | Single shape carried through grouping, hierarchy assembly, rewrite, export | `pdf_chapter_grouper`, `pdf_hierarchy_assembler`, exporter |
| `build_sections(*, boundaries, validated_headings, lines, drop_empty=True)` → `List[PartitionedSection]` | For each boundary pair, join non-noise lines into `body` and collect validated headings inside the span as `inner_headings` with score / confidence / signals | Keeps the inner hierarchy visible to the rewrite LLM (which the legacy pipeline flattens) | `pipeline_signal_sections.run_signal_pipeline` |

### File: `pdf_chapter_grouper.py`

- **One-line purpose:** Group partitioned sections under chapters using PDF structural markers only.
- **Why this file exists:** The legacy `chapter_hierarchy_builder.py` + `chapter_placement.py` + `hierarchy_openai_refinement.py` chain renumbers, regroups, and renames chapters. This module replaces them with a single deterministic pass that mirrors the PDF.

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `GroupedChapter` (dataclass) | `chapter_id, heading (verbatim), level, page_start, page_end, line_id_start, sections, assignment_method` | Mirrors a PDF chapter exactly; `assignment_method` records which rule fired so reruns are auditable | `pdf_hierarchy_assembler`, exporter |
| `find_chapter_marker_line_ids(lines)` → `List[int]` | Return the line ids in `ctx.lines` whose text matches `is_structural_marker` and is not noise | Drives the marker-based grouping path | `group_by_markers`, `group_into_chapters` |
| `group_by_markers(*, sections, marker_line_ids, line_text, line_page)` → `List[GroupedChapter]` | Each marker-aligned section starts a chapter; sections after it (until the next marker) belong to that chapter; sections **before** the first marker open an implicit "Front Matter / first-section-titled" chapter | Preserves verbatim PDF order and titles | `group_into_chapters` |
| `group_by_promotion(*, sections, section_scores, promote_h1_count)` → `List[GroupedChapter]` | When no PDF markers exist, promote the top-N highest-scored sections to L1 chapters | Fallback that still avoids inventing titles (uses the verbatim heading of the promoted section) | `group_into_chapters` |
| `group_into_chapters(*, sections, lines, promote_h1_count=8, section_scores=None)` → `(List[GroupedChapter], strategy)` | Top-level entry: try markers, fall back to promotion, finally degrade to a single chapter | One callable so the runner stays small | `pipeline_signal_sections.run_signal_pipeline` |

### File: `pdf_hierarchy_assembler.py`

- **One-line purpose:** Build the final `signal_hierarchy.json` dict and verify titles are non-empty.
- **Why this file exists:** Consolidates chapters + boundaries + stats into the single artifact the rewrite engine and exporter both consume; isolating the schema here keeps callers small.

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `assemble_hierarchy(...)` → `Dict` | Produce the payload (book_title, source_pdf, meta, boundaries, chapters) with PDF-mirror counts | The single source of truth for downstream stages | runner |
| `assert_pdf_titles_preserved(hierarchy)` → `List[str]` | Returns a list of problem messages when any chapter/section/inner heading text is empty | Cheap defensive check before rewrite (per acceptance criterion SS-02) | runner |

### File: `signal_logger.py`

- **One-line purpose:** Write JSON artifacts to a dedicated `logs/run_signal_<ts>/` directory.
- **Why this file exists:** Existing audit / re-export scripts scan `logs/run_<ts>/`. Keeping signal artifacts in a separate prefixed tree guarantees we never confuse those tools (acceptance criterion SS-04).

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `resolve_signal_log_dir(*, explicit=None)` → `Path` | Create + return `logs/run_signal_<utc>/` (or an explicit override) | Single resolver shared by the runner and tests | runner |
| `SignalRunLogger(run_dir)` | Thin writer with `write_boundaries`, `write_hierarchy`, `write_rewritten`, `write_run_meta` | Stable filenames (`signal_boundaries.json`, etc.) so reruns are deterministic | runner, tests |

---

## 2. `backend/src/modules/generation/signal_rewrite/`

### File: `__init__.py`
- **Purpose:** Public module list for the rewrite layer.

### File: `hierarchy_prompt.py`

- **One-line purpose:** Build the structural-aware system + user prompts the LLM receives for one section.
- **Why this file exists:** The legacy `rewrite_prompts.py` flattens subheadings into prose and never tells the model the parent chapter path. This module sends the full ladder (book → chapter L1 → section L2) plus inner-heading hints with scores, plus previous/next section headings and tails — the information the user explicitly asked for.

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `SIGNAL_REWRITE_SYSTEM_TEMPLATE` (str) | Universal output rules: do not print the section title; use `###` only for real inner sub-topics; English only; no admin/syllabus blocks; no outer code fence | Encodes the user's "preserve hierarchy, decide which inner hints are real" requirement | `build_signal_system_prompt` |
| `build_signal_system_prompt(*, user_instruction)` → str | Inject the user-style instruction into the universal template | One stable system message per run | rewrite engine |
| `build_signal_section_prompt(...)` → str | Build the per-section user prompt with parent path, inner-heading hints (text + line + page + confidence + signals), prev/next section heading + overlap, and the source body | The signal pipeline's central design contract | rewrite engine |

### File: `inner_heading_decider.py`

- **One-line purpose:** Post-process the LLM's per-section answer and validate `###` usage.
- **Why this file exists:** The system prompt asks the model to be careful; this is the deterministic safety net that downgrades any `### ...` the model invents to plain bold, strips an echoed title, and unwraps a stray outer code fence. Without it we have no guarantee that SS-03 holds.

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `DeciderReport` (dataclass) | `inner_emitted, inner_accepted, inner_downgraded, top_level_stripped, fence_unwrapped, notes` | Persisted in `signal_rewritten.json` for auditability | rewrite engine, exporter |
| `validate_inner_headings(*, generated_text, section_heading, inner_headings)` → `(str, DeciderReport)` | (1) strip outer fence (keep mermaid), (2) strip an echoed `# / ##` title, (3) downgrade any `###` whose text is not in `inner_headings` | Enforces SS-03 deterministically | rewrite engine |

### File: `rewrite_engine.py`

- **One-line purpose:** Parallel rewrite driver — one OpenRouter call per section, then `inner_heading_decider`.
- **Why this file exists:** Keeps prompt construction (`hierarchy_prompt`) and validation (`inner_heading_decider`) separate from concurrency and provider plumbing. Re-uses the existing `LlmChatClient` (no fork of the HTTP layer).

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `DEFAULT_MODEL = "google/gemini-2.5-flash-lite"` | Confirmed user request (corrected from `-preview` to the GA slug after OpenRouter HTTP 400) | Single source of truth | settings resolver |
| `SectionRewriteResult` (dataclass) | `chapter_id, section_id, heading, model, success, body_md, elapsed_s, decider, error, attempts` | What the runner persists into `signal_rewritten.json` | runner, exporter |
| `resolve_signal_rewrite_settings()` → dict | Reads `SIGNAL_REWRITE_*` env keys with sane fallbacks (incl. `REWRITE_USER_INSTRUCTION` fallback) | One resolver shared by runner + tests | runner |
| `rewrite_signal_sections(*, hierarchy, settings=None, on_progress=None, client=None)` → `List[SectionRewriteResult]` | Flatten the hierarchy into per-section jobs, dispatch in a `ThreadPoolExecutor`, post-validate, return results in PDF order | The single entry point for SS-P1 | runner, tests |

Private helpers (`_flatten_sections_with_chapters`, `_build_job_prompt`, `_run_one`, `_SectionJob`) encode the job-decomposition logic and per-section retry; they are not part of the public API.

---

## 3. `backend/src/modules/export/signal_export/`

### File: `__init__.py`
- **Purpose:** Package marker.

### File: `pdf_mirror_docx.py`

- **One-line purpose:** Assemble PDF-mirror Markdown + render DOCX through the project's standard renderer.
- **Why this file exists:** Re-using `markdown_docx_renderer.export_markdown_file_to_docx` keeps the DOCX visual style consistent with the legacy pipeline while letting us own the Markdown assembly (so we can guarantee verbatim chapter / section headings and a `[signal] rewrite unavailable` callout when a section's LLM call failed).

| Symbol | Purpose | Why | Called by |
|---|---|---|---|
| `assemble_signal_markdown(*, hierarchy, rewritten_by_section_id, book_title=None, include_toc=True)` → str | Build the Markdown: centered cover title, TOC table (`C1. <heading> ¦ pages`), then `# Chapter` / `## Section` / body | Mirrors the PDF tree 1-to-1 and uses the rewritten body when available | runner, tests |
| `export_signal_docx(*, markdown_text, output_path, theme=None)` → str | Wrap `markdown_docx_renderer.export_markdown_file_to_docx` | Reuses the project's docx theme + page-break handling | runner |
| `write_signal_markdown(*, markdown_text, output_path)` → str | Write the assembled Markdown to disk | Useful for `--skip-rewrite` and tests | runner, tests |

---

## 4. `backend/scripts/pipeline_signal_sections.py`

- **One-line purpose:** End-to-end runner — the new command the user invokes.
- **Why this file exists:** Owns the orchestration sequence (early structure → signal hierarchy → rewrite → export) and reads only `SIGNAL_*` env keys. Keeps every existing script unchanged.

| Symbol | Purpose | Why |
|---|---|---|
| `SIGNAL_STAGES` (tuple) | The exact early-stage list shared with the legacy pipeline (extract → normalize → noise → score → gate → continuity → fragments → toc clean / detect / flag / resolve → finalize → validate titles) | The signal pipeline must consume the same trusted heading set the legacy pipeline produces, *but stop before* `stage_build_book_structure` runs |
| `resolve_signal_structure_settings()` → dict | Read `SIGNAL_BOUNDARY_*` / `SIGNAL_PROMOTE_H1_COUNT` / `SIGNAL_OUTPUT_SUFFIX` / `SIGNAL_EXPORT_DOCX` env vars | Single resolver for the structure half |
| `run_signal_pipeline(pdf_path, *, enable_logs=True, skip_rewrite=False, output_dir=None, log_dir=None)` → dict | Programmatic entry point used by both the CLI and tests | Returns the run-meta payload so tests can assert |
| `main(argv=None)` → int | CLI: parses `pdf`, `--skip-rewrite`, `--no-logs`, `--output-dir`, `--log-dir` | The user-facing command |

---

## 5. Tests

| File | What it covers |
|---|---|
| `backend/tests/unit/test_signal_classifier.py` | Structural-marker regex coverage, percentile cutoff math, min-score override, dedup of structural ∪ percentile, empty input |
| `backend/tests/unit/test_signal_partitioner.py` | Section span boundaries, inner-heading attachment with metadata, noise line exclusion, drop-empty behavior, verbatim heading preservation |
| `backend/tests/unit/test_pdf_chapter_grouper.py` | Marker detection across CHAPTER/MODULE/UNIT, marker-based grouping, pre-marker implicit chapter, promotion fallback, verbatim chapter titles |
| `backend/tests/unit/test_signal_rewrite_prompt.py` | System + user prompt assembly (parent path, inner-heading hints with line/page/confidence, prev/next overlap), decider behaviour (top-title strip, fence unwrap, undeclared `###` downgrade, mermaid retention, empty output) |
| `backend/tests/unit/test_signal_pipeline_end_to_end.py` | Structure → mocked LLM (stub `chat_with_provider`) → markdown assembly + signal logger artifacts on disk |

All five test files were added at 2026-06-16; 33 new tests pass and 0 of the 378 pre-existing unit tests regress.

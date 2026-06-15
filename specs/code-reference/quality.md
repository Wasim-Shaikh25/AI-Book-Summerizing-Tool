# Code Reference — Quality

> **Package:** `backend/src/modules/quality/`  
> **Module spec:** [../modules/quality.md](../modules/quality.md)  
> **Requirements:** [../../ai-agent-workflow/requirements-notes-quality.md](../../ai-agent-workflow/requirements-notes-quality.md)

---

## Files

| File | Purpose | Why separate file |
|------|---------|-------------------|
| `service.py` | Thin entry `run_quality_audit` | Pipeline/scripts call one function |
| `analyzer.py` | Build full text/json/md reports | Orchestration separate from heuristics |
| `heuristics.py` | Heading/body scoring rules | Reused by analyzer and batch compare |
| `heading_acceptance.py` | AC-01…AC-05, AC-07 on export titles | Structural gate distinct from line audit |
| `line_audit.py` | Per-line body scan | Primary content-quality gate |
| `llm_insights.py` | Optional LLM narrative | Isolated — can disable without breaking deterministic audit |
| `models.py` | `Report`, `BookAuditResult` dataclasses | Typed report structure |
| `__init__.py` | Re-exports public API | `compare_notes_quality.py` compatibility |

---

## `service.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `audit_enabled()` | Read `NOTES_QUALITY_AUDIT` env | Skip audit in fast dev runs | `run_full_openai_pipeline.py` |
| `run_quality_audit(...)` | Run analyzer + optional LLM, write reports | Single post-export hook | Pipeline, `run_notes_quality_audit.py` |

---

## `analyzer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_report(...)` | Per-book deterministic report sections 1–15 | Main audit output; coverage via `resolve_rewritten_map` (sid-first) | `run_quality_audit` |
| `build_combined_report(...)` | Multi-book side-by-side summary | Batch pipeline comparison | `run_batch_pipeline.py` |
| `run_batch_audit(manifest)` | Audit many outputs from manifest JSON | Regression across PDF set | Batch scripts |
| `pdf_match_heading(...)` | Check if heading text appears in PDF pages | Detect renamed vs missing headings; renamed ≠ fail. Returns `grounded_in_source` for clean titles covered by source but not verbatim in PDF (`NOTES_QUALITY_PDF_MATCH_SOURCE_GROUNDING`) — not a failure | `build_report` |
| `_title_grounded_in_source(title, source)` | ≥60% of title content words present in section source | Reward cleaned/derived titles instead of failing them | `pdf_match_heading` |
| `resolve_chapter_hierarchy_artifact_safe(log_dir)` | Load hierarchy for coverage checks | Needs section count from latest 15j/15e | Coverage, AC-05 |
| `flat15e_from_chapters(hierarchy)` | Flatten chapter tree to section list | Uniform section iteration | Line audit, repetition |
| `aggregate_batch_summary(results)` | Table rows for batch markdown | Human-readable regression summary | Batch pipeline |

---

## `heuristics.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `classify_heading(title)` | Label: `looks_ok`, `statute_prose`, `weak`, etc. | AC-03/AC-04 use same rules as pipeline | `heading_acceptance`, analyzer §4 |
| `chapter_mirrors_first_section(ch, threshold)` | Detect parent-mirror | Chapter title ≈ first section confuses study outline | Analyzer §5, AC |
| `find_parent_mirror_chapters(hierarchy)` | List all mirrors | Batch summary metric | `build_report` |
| `compute_verdict_scores(dimensions)` | Weight PASS/WARN/FAIL → overall | Line quality + heading AC weighted | `build_report` |
| `detect_syllabus_noise_in_body(text)` | Admin/syllabus phrases in bodies | Syllabus should not appear in rewritten notes | Analyzer §8 |
| `heading_sim(a, b)` | Normalized similarity | Repetition + mirror detection | Multiple dimensions |

---

## `heading_acceptance.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `parse_markdown_headings(md)` | Extract `#` / `##` from export MD (strips `<!-- sid: -->` tags) | AC runs on user-visible export titles | `evaluate_heading_acceptance` |
| `evaluate_heading_acceptance(md, docx, hierarchy, bodies)` | Run AC-01…AC-05, AC-07 | Enforces pipeline heading fixes in deliverables | `build_report` §15 |
| `format_acceptance_report(result)` | Human-readable AC block | `.quality_report.txt` | `build_report` |

**AC rationale:**

| AC | Why |
|----|-----|
| AC-01 | `CHAPTER I:` lines are structural breaks, not study section titles |
| AC-02 | PDF extraction leaks currency/page-footer fragments as headings |
| AC-03 | Bare acts export `Explanation:` / `Section N: … —` as headings without cleanup |
| AC-04 | Display resolver must match same rules as export |
| AC-05 | Rewrite must cover ≥98% of hierarchy sections |
| AC-07 | Thin bodies indicate failed or skipped rewrite |

---

## `line_audit.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `line_audit_enabled()` | `NOTES_QUALITY_LINE_AUDIT` | Disable for fast runs | `build_report` |
| `line_audit_strict()` | Stricter thresholds | CI/regression mode | `audit_section_body` |
| `semantic_grounding_enabled()` | `NOTES_QUALITY_SEMANTIC_GROUNDING` | Accept paraphrase via MiniLM, still flag drift | `audit_section_body` |
| `_SemanticGrounder(source, enabled)` | MiniLM source-sentence grounding; `grounded(line)` | Suppress `low_source_overlap` for grounded paraphrase | `audit_section_body` |
| `audit_section_body(section_id, body, source_preview, semantic, source_low_grounding)` | Per-section line scan | Primary content quality gate; skips overlap checks for low-grounding sources | `audit_all_sections` |
| `audit_all_sections(sections, previews, semantic)` | All sections → `BookLineAudit`; computes per-section low-grounding | Report §15 line block | `build_report` |
| `format_line_audit_report(audit)` | Text formatting | Report output | `build_report` |

**Line issue types (why):**

| Issue | Why flagged |
|-------|-------------|
| Meta filler | "This chapter covers…" adds no study content |
| Heading echo | Body repeats `##` title — template artifact |
| Thin bullet | Single-word bullets look like broken prose |
| Standalone bold | Fake subheadings when book mode expects prose |
| Low source overlap | Drift from PDF source preview |
| Bullet-only section | Book mode expects continuous paragraphs |

---

## `llm_insights.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `llm_insights_enabled()` | `NOTES_QUALITY_LLM` env | Rate limits / cost control | `run_quality_audit` |
| `generate_llm_insights(summary_json)` | Narrative + universal fix suggestions | Human-readable action items; no legal claims | `run_quality_audit` |

---

## `models.py`

| Symbol | Purpose | Why |
|--------|---------|-----|
| `BookAuditResult` | Per-book scores + verdict | Typed batch aggregation |
| `Report` | Full report payload | JSON serialization |

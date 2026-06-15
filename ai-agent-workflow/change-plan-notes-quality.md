# Change Plan — Notes Quality (Subject-Agnostic)

> **Source observation:** `output/audit/bareact-140_quality_report.txt`  
> **Hard rule:** No code path may name or detect a subject (law, medicine, pharma, engineering, …). Every behaviour change is driven by **measured document properties** that apply equally to any PDF.  
> **Authority:** `specs/index.md` is the SDD; this file is the plan only. Specs update when each phase lands.

---

## 1. Failing dimensions on the last run

| Dimension | Result | Universal symptom |
|-----------|--------|---------------------|
| Coverage | 22 / 57 mapped (39 %) | Many exported sections have empty bodies |
| Completeness | AC-05 FAIL | Auto-retry of missing sections is not invoked inline |
| Fidelity | avg keyword overlap 13 % | Rewrites drift away from the source they were given |
| Heading acceptance | AC-02 / 03 / 04 FAIL (11 noisy titles) | Display layer has no late guard |
| PDF match | 13 titles `not_in_pdf` | LLM title edits are not verified against source text |
| Parent mirror | 2 chapters | 1-section chapters create a duplicate `##` |
| Line quality | 17 FAIL sections (`section_drift`, `low_source_overlap`) | Parallel rewrite context overlap bleeds into wrong section |

All seven symptoms are **document-shape problems**, not subject problems.

---

## 2. Replace subject names with one measured profile

### 2.1 New module: `backend/src/modules/ingestion/document_profile.py`

A **measured** profile produced during ingestion. No subject keywords, no example texts, no domain regex. Computed from the normalized lines and PDF stats already produced by `stage_ingest_pdf` and `stage_finalize_heading_list`.

```python
@dataclass(frozen=True)
class DocumentCharacterProfile:
    page_count: int
    line_count: int

    heading_density: float            # headings / page
    median_section_body_chars: int    # median chars between adjacent headings
    short_section_ratio: float        # share of section bodies under SHORT_BODY_CHARS
    prose_paragraph_ratio: float      # share of lines that look like prose paragraphs
    enumerated_clause_ratio: float    # share of lines opening with "<N>." / "(<n>)" / lettered list
    avg_line_length: float
    title_token_median: int           # median word count of accepted headings

    # Derived knobs (no subject naming) — every consumer reads these.
    min_section_body_chars: int       # threshold for build_ultimate_sections
    rewrite_max_source_chars: int     # cap fed to LLM
    rewrite_overlap_chars: int        # adjacent-section context
    rewrite_max_tokens: int           # output token budget per section
    enforce_single_topic_prompt: bool # tighten prompt when sections are short
    require_strict_heading_match: bool# fall back to local title if LLM-edited title not in PDF
```

Detection is **continuous**: every consumer reads its number from the profile, no `if subject == ...` branching.

### 2.2 How the numbers are produced (universal)

| Signal | Where it is measured | Method |
|--------|----------------------|--------|
| `heading_density` | `final_headings` length / `page_count` | Already available — no new parser. |
| `median_section_body_chars` | Distances between adjacent accepted heading `line_id`s | `statistics.median()` on existing line offsets. |
| `short_section_ratio` | Same population vs `SHORT_BODY_CHARS` (default 400) | One pass over headings. |
| `prose_paragraph_ratio` | Share of lines whose stripped text ends in `.` and has ≥ 8 words | Universal — no domain keywords. |
| `enumerated_clause_ratio` | Share of lines matching general patterns: `^\d+\.\s`, `^\(\w{1,4}\)\s`, `^[A-Z]\.\s` | Generic numeric / lettered list openers — present in law, formularies, drug indications, lab protocols, engineering specs. |
| `title_token_median` | Word count of accepted headings | `statistics.median()`. |

### 2.3 How the knobs are derived (universal mapping)

The mapping is a **smooth function**, not a switch:

```text
density_factor   = clamp(heading_density / 1.0, 0.3, 3.0)
brevity_factor   = 1 - short_section_ratio        # 0..1
prose_factor     = prose_paragraph_ratio           # 0..1

# Smaller min when sections are short and headings are dense — keeps clause-heavy
# documents (any domain) from losing entries.
min_section_body_chars = round(base_min * brevity_factor * (1 / density_factor))

# Less overlap when sections are short — neighbour context becomes noise.
rewrite_overlap_chars  = round(base_overlap * brevity_factor * prose_factor)

# Fewer output tokens when source is small — prevents padding/hallucination.
rewrite_max_tokens     = clamp(round(base_max_tokens * (median_section_body_chars / base_median)), 400, base_max_tokens)

# Strict per-section prompt when sources are short OR enumerated clauses dominate.
enforce_single_topic_prompt = (short_section_ratio > 0.5) or (enumerated_clause_ratio > 0.4)

# Verify LLM-edited titles when local headings are short (less semantic room).
require_strict_heading_match = (title_token_median <= 6) or (heading_density > 1.0)
```

All `base_*` constants live in `default.yaml` under a new `document_profile:` block — overridable per deployment, never per subject.

### 2.4 Wiring

| Consumer | Today | After |
|----------|-------|-------|
| `book_assembler.build_ultimate_sections` | Reads `min_heading_fragment_chars` from `config.resolve_ultimate_thresholds()` | Reads `profile.min_section_body_chars` |
| `parallel_rewrite.resolve_context_overlap_chars` | Reads env / config | Reads `profile.rewrite_overlap_chars` (env override still wins) |
| `RewriteEngine.rewrite_sections` (`max_tokens`) | Constant default 1800 | `profile.rewrite_max_tokens` |
| `rewrite_prompts.rewrite_system_prompt` | Static guardrails | When `profile.enforce_single_topic_prompt`, append one neutral line: *"Discuss only the topic named in the section heading. Do not summarise adjacent sections."* |
| `hierarchy_openai_refinement` + `subheading_refinement` | Accept LLM-edited title unconditionally | When `profile.require_strict_heading_match`, accept only if the edited string occurs as a substring on any PDF page within the section's page span; else revert to the cleaned local title |

Nothing above references a subject. A 600-page constitutional law text, a drug formulary, a maths textbook with theorem clauses, and a clinical guidelines PDF all yield different numeric profiles and therefore different behaviour — but the same code path.

### 2.5 Persistence and provenance

Per rule 07 (data provenance):
- Profile saved to the run dir as `s00_document_profile.json` (new log key `document_profile`, registered in `stage_catalog.py` and `stage_registry.py`).
- Every downstream artifact already carries `run_id`; consumers read the profile via a single helper `load_document_profile(run_dir)`.

---

## 3. Coverage fixes (P0 — biggest win, lowest risk)

All universal — every fix triggers from measured signals or pipeline state, never from text patterns.

### 3.1 Stop silent drops in export

`document_formatter.chapter_blocks_from_hierarchy` currently does `continue` when both rewrite body and fragment preview are empty (lines 273–296). Replace with one of:

| Mode | Behaviour | Rule reference |
|------|-----------|----------------|
| `EXPORT_MISSING_BODY_MODE=placeholder` (default) | Emit a one-line placeholder paragraph that names the section and references the source page. **Section count preserved.** | rule 12 (no overbuild — pick a clear default) |
| `EXPORT_MISSING_BODY_MODE=fail` | Raise; caller decides retry policy. | rule 04 (no fake success) |
| `EXPORT_MISSING_BODY_MODE=skip` | Today's behaviour, kept for compatibility. | — |

The placeholder text is generic: *"Source text not available for this section — refer to page N of the source document."* No subject words.

### 3.2 Inline auto-retry of missing/short sections

`rewrite_missing_sections.py` already implements this for offline recovery. Promote the core function (`retry_missing_sections`) into `generation/rewrite.py` and call it from `RewriteEngine.run` right after the first parallel pass:

```text
parallel_rewrite() → validate_rewrite_coverage(min_coverage=0.98)
  → if missing_section_ids: retry_missing_sections(ids, ...)
  → re-assemble markdown only after retry.
```

Caps:
- `REWRITE_AUTO_RETRY_ENABLED` (default true)
- `REWRITE_AUTO_RETRY_MAX_PASSES` (default 1)
- `REWRITE_AUTO_RETRY_MIN_COVERAGE` (default 0.95) — only retries below this.

No subject-specific behaviour; this loop is just "if some sections came back empty, ask the model again with overlap disabled."

### 3.3 Keep short-body sections in `build_ultimate_sections`

Today `_is_high_probability_row` uses one global `min_heading_fragment_chars`. Replace with `profile.min_section_body_chars` (§2.4). This recovers many of the 1099 currently dropped headings without touching its rejection logic for actual noise.

---

## 4. Fidelity fixes (P1 — solves the 13 % overlap problem)

### 4.1 Post-rewrite fidelity gate

Same overlap calculation the audit uses (`low_source_overlap` in `quality/line_audit.py`) becomes available to the generation layer via a new helper `generation/rewrite_fidelity.py`:

```python
def section_overlap_score(*, source: str, generated: str) -> float: ...
def needs_regeneration(score: float) -> bool: ...
```

Wiring in `parallel_rewrite._run`:

1. Generate.
2. Compute `score = section_overlap_score(source, generated)`.
3. If `score < REWRITE_FIDELITY_MIN_OVERLAP` (default 0.30), regenerate **once** with:
   - `overlap_chars = 0` (no neighbour context — kills the drift cause)
   - `temperature = 0.1` (or whatever floor the provider supports)
   - Prompt prefix: *"Stay strictly within the provided source. Do not include facts from previous or next sections."*
4. Keep whichever attempt scored higher.

The threshold is numeric and lives in `default.yaml`; nothing subject-specific.

### 4.2 Overlap and token budgets from the profile

Today `REWRITE_CONTEXT_OVERLAP_CHARS=600` is fixed for every document. With §2 it becomes `profile.rewrite_overlap_chars` — automatically near zero for clause-dense documents (any domain) and full size for prose-heavy ones. Same for `max_tokens`.

### 4.3 Heading binding in the prompt

`rewrite_prompts.rewrite_system_prompt` already has a "do not invent facts" guardrail. When `profile.enforce_single_topic_prompt`, append one neutral line: *"Discuss only the topic named in the section heading provided to you. Do not summarise the previous or next section."*

No domain phrases.

---

## 5. Heading acceptance fixes (P1 — solves AC-02 / 03 / 04)

### 5.1 Display-layer late guard

`document_formatter._display_heading` (lines 217–238) returns whatever `resolve_section_display_heading` produces. Add a single post-step using existing classifiers from `quality/heading_acceptance.py`:

```text
display = resolve_section_display_heading(...)
verdict = classify_display_heading(display)        # already exists in quality/
if verdict != "looks_ok":
    display = partition_heading_to_study_title(parent_heading) + f" (p. {page_number})"
```

The classifier already operates on generic shape (noise patterns, prose detection, fragments). It does not embed domain words; we just call it from a layer that previously did not.

### 5.2 PDF-anchored title acceptance

Inside `hierarchy_openai_refinement` and `subheading_refinement`, when `profile.require_strict_heading_match`:

1. After LLM proposes a new title, search the original `lines` slice within the section's page range for any normalized substring of the new title.
2. If no match, revert to the cleaned local title.

Pure substring search on `NormalizedLine.text` — no domain knowledge. Eliminates the 13 `not_in_pdf` titles regardless of subject.

---

## 6. Mirror fix (P2)

`chapter_placement.enforce_chapter_structure` already handles parent-mirror for multi-section chapters. Add the missing case:

```text
if len(chapter.sections) == 1 and similar(chapter.heading, chapter.sections[0].heading):
    chapter.heading  = best_label_from(chapter.sections[0])    # uses existing study_title helper
    chapter.sections = chapter.sections[0].subheadings or []    # promote subheadings if any
```

`best_label_from` uses the existing universal cleaner; no domain text.

---

## 7. Observability

Add three audit-facing fields so future runs are debuggable without re-reading code:

| Field | Source | Where shown |
|-------|--------|-------------|
| `document_profile` block | new s00 artifact | `quality_report.txt` §1 |
| `rewrite_attempts_per_section` | per-section counter from rewrite engine | section log in run dir |
| `auto_retry_summary` | `{missing_before, missing_after, regenerated_for_drift}` | `quality_report.txt` §7 |

---

## 8. Configuration surface (new keys, all generic)

`backend/config/default.yaml` additions — every key applies to all documents:

```yaml
document_profile:
  short_body_chars: 400
  base_min_section_body_chars: 200
  base_rewrite_overlap_chars: 600
  base_rewrite_max_tokens: 1800
  base_median_section_body_chars: 1200

rewrite:
  auto_retry_enabled: true
  auto_retry_max_passes: 1
  auto_retry_min_coverage: 0.95
  fidelity_min_overlap: 0.30
  fidelity_regenerate_temperature: 0.1

export:
  missing_body_mode: placeholder   # placeholder | fail | skip
```

Env overrides: `REWRITE_AUTO_RETRY_*`, `REWRITE_FIDELITY_*`, `EXPORT_MISSING_BODY_MODE`. No subject-named keys.

---

## 9. File-by-file change list

| Path | Change | Phase |
|------|--------|-------|
| `backend/src/modules/ingestion/document_profile.py` | New module — `DocumentCharacterProfile`, `compute_profile()`, `load_document_profile()` | P0 |
| `backend/src/modules/pipeline/stage_catalog.py` | Register semantic log key `document_profile` + display row | P0 |
| `backend/src/modules/pipeline/stage_registry.py` | Map `document_profile` → `s00_document_profile.json` | P0 |
| `backend/src/modules/pipeline/stages.py` | New `stage_compute_document_profile` after `stage_ingest_pdf` (writes artifact + attaches to context) | P0 |
| `backend/src/modules/pipeline/context.py` | Add `document_profile: DocumentCharacterProfile \| None` field | P0 |
| `backend/src/modules/structure/final_structuring/book_assembler.py` | Read `min_section_body_chars` from profile instead of constant | P0 |
| `backend/src/modules/export/document_formatter.py` | Implement `EXPORT_MISSING_BODY_MODE`; add display-layer late guard | P0 + P1 |
| `backend/src/modules/generation/rewrite.py` | Read `max_tokens` from profile; call inline auto-retry | P0 + P1 |
| `backend/src/modules/generation/parallel_rewrite.py` | Use profile overlap; run fidelity gate per section | P1 |
| `backend/src/modules/generation/rewrite_fidelity.py` | New helper module (extract `low_source_overlap` math from `quality/line_audit.py` into shared location, import from both) | P1 |
| `backend/src/modules/generation/rewrite_prompts.py` | Append single neutral guardrail when `enforce_single_topic_prompt` | P1 |
| `backend/src/modules/structure/final_structuring/hierarchy_openai_refinement.py` | PDF-anchored title acceptance gate | P1 |
| `backend/src/modules/structure/final_structuring/subheading_refinement.py` | Same gate | P1 |
| `backend/src/modules/structure/final_structuring/chapter_placement.py` | 1-section mirror fix | P2 |
| `backend/src/modules/quality/analyzer.py` | Print document profile + auto-retry summary in report | P1 |
| `backend/config/default.yaml` | New `document_profile`, `rewrite`, `export` keys | P0 |
| `backend/tests/unit/test_document_profile.py` | Profile detection on synthetic line sets (prose-heavy / clause-heavy / mixed) | P0 |
| `backend/tests/unit/test_rewrite_fidelity.py` | Drift detection + regenerate trigger | P1 |
| `backend/tests/unit/test_export_missing_body_mode.py` | Placeholder + fail + skip behaviours | P0 |
| `backend/tests/unit/test_chapter_single_section_mirror.py` | 1-section mirror collapse | P2 |

---

## 10. Spec updates required (per rule 13, after implementation lands)

| Spec | Update |
|------|--------|
| `specs/modules/ingestion.md` | New `document_profile` step |
| `specs/modules/llm-generation.md` | New §4b "Fidelity gate" + auto-retry inline |
| `specs/modules/export.md` | `EXPORT_MISSING_BODY_MODE` + display guard |
| `specs/modules/structure-extraction.md` | PDF-anchored title acceptance + 1-section mirror |
| `specs/modules/parameters-config.md` | New `document_profile.*`, `rewrite.auto_retry_*`, `rewrite.fidelity_*`, `export.missing_body_mode` |
| `specs/modules/stage-catalog.md` | Add `document_profile` log key |
| `specs/modules/logging-debug.md` | `s00_document_profile.json` artifact row |
| `specs/code-reference/ingestion.md` | `document_profile.py` symbols |
| `specs/code-reference/generation.md` | `rewrite_fidelity.py` + inline retry symbols |
| `specs/code-reference/pipeline.md` | New stage function row |
| `specs/code-reference/export.md` | Display guard symbols |
| `specs/code-reference/structure.md` | PDF-anchored gate symbols |
| `specs/code-reference/quality.md` | Note that `low_source_overlap` math is shared with rewrite layer |
| `specs/change-log.md` | One entry per phase |
| `specs/testing.md` | Four new test files |
| `ai-agent-workflow/requirements-notes-quality.md` | Add fidelity gate + PDF-anchored title as requirements |
| `ai-agent-workflow/tasks.md` | Tasks per phase |

---

## 11. Acceptance criteria (verifiable, subject-independent)

Re-running any PDF must satisfy:

| ID | Criterion |
|----|-----------|
| NQ-01 | `mapped_sections / total_sections ≥ 0.95` |
| NQ-02 | `avg keyword overlap on mapped sections ≥ 0.30` |
| NQ-03 | `0` titles classified as `not_in_pdf` when `require_strict_heading_match` is on |
| NQ-04 | `0` chapters where `chapter.heading == chapter.sections[0].heading` |
| NQ-05 | Export never silently drops a hierarchy section (when `missing_body_mode != skip`) |
| NQ-06 | `run dir` contains `s00_document_profile.json` for every run with logs enabled |
| NQ-07 | No new env key, prompt string, or regex contains a subject name (`law`, `medical`, `pharma`, `engineering`, `bare`, `statute`, `section`, `clause`, `drug`, `theorem`, …). |

NQ-07 is enforced by a unit test that greps the diff for those words inside the listed files.

---

## 12. Execution order

| Phase | Branch | Deliverable |
|-------|--------|--------------|
| P0 | `notes-quality/p0-coverage` | Document profile + inline auto-retry + missing-body mode + tests + specs + change-log |
| P1 | `notes-quality/p1-fidelity` | Fidelity gate + heading display guard + PDF-anchored title + tests + specs + change-log |
| P2 | `notes-quality/p2-mirrors` | 1-section mirror collapse + tests + specs + change-log |

Each phase ends with the full unit suite green and a re-audit of `bareact-140.pdf` (treated as one of several validation PDFs, not as a special case) showing measurable movement on NQ-01…NQ-06.

---

## 13. Out of scope

- No subject-specific prompts, regex, or profiles.
- No per-PDF tuning files.
- No new model dependencies.
- No changes to the structure stage names introduced in `stage-catalog.md`.
- No changes to log artifact filenames.

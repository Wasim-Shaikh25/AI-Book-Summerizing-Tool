# Restructure plan: plugin pipeline, trace-only scope, LLM removal

This document answers: **(1)** what `run_toc_trace` actually needs, **(2)** which code is redundant or LLM-only, **(3)** a target layout where **one thin orchestrator** wires **stages as plugins** with **no business logic in the shell**, and **(4)** safe incremental steps.

Scope note: **`run_toc_trace` still depends on ingestion** (`extract_pdf` → `normalize_text` → …). Excluding the `ingestion/` folder from *physical* deletion; the restructure is about **clear ownership and imports**, not removing PDF parsing.

---

## 1. What `run_toc_trace` actually calls

```
src/debug/run_toc_trace.py::run
  → src/core/pipeline.py::run_pipeline(enable_logs=True, persist_to_db=True)
  → [optional] src/debug/visualizer.py::visualize_run
```

So the **minimal production dependency** is everything **transitively imported by** `run_pipeline`, plus **visualizer** (debug only), plus **storage** when `persist_to_db=True`.

### 1.1 Transitive closure (keep / consolidate)

| Area | Modules on the hot path |
|------|-------------------------|
| Ingestion | `pdf_extractor`, `text_normalizer`, `layout_enrichment` |
| Utils | `pdf_reader` (via `pdf_extractor`); optional `ocr_reader` only if PDF path uses OCR |
| Core models | `src/core/models.py` (used almost everywhere after normalize) |
| Structure | `noise_filter`, `candidate_scoring`, `heading_validity_gate`, `fragments`, `toc_cleaning`, `toc_repeat_detection`, `logging/pipeline_logger` |
| Core | `pipeline.py`, `models.py` |
| Storage (if persist) | `knowledge_store`, `book_repository`, `toc_repository`, `schema` |
| Debug | `run_toc_trace`, `visualizer` |

### 1.2 Duplicate / split definitions (fix when restructuring)

- **`NormalizedLine` in two places:** `src/domain/document.py` and `src/core/models.py`. `pdf_extractor` returns **`domain.document.NormalizedLine`**; `layout_enrichment` builds **`core.models.NormalizedLine`**. The pipeline normalizes via `text_normalizer`, which expects `extract_pdf`’s tuple. This works only if types are compatible duck-typing-wise — **merge to a single module** (e.g. `src/core/types.py` or keep only `core/models.py`).

- **`src/core/candidate_scoring.py`** — **not imported anywhere**; **`src/structure/candidate_scoring.py`** is the one `run_pipeline` uses. **Delete or merge** the core duplicate.

- **`src/structure/heading_candidates.py`** — imports `from .models import ...` but **`src/structure` has no `models.py`** (broken / dead for normal imports). **`collect_heading_candidates` is not used** by `run_pipeline`. Treat as **orphan or fix import** if you still want the heuristic elsewhere.

---

## 2. LLM-related code: what to remove or isolate

`run_pipeline` **does not import** `src/LLMAdaptor`. These files **do** depend on LLMs (candidates for **deletion** or move to `archive/` if you want history):

| Module | Role |
|--------|------|
| `src/LLMAdaptor/**` | Entire package (client, providers, prompts) |
| `src/structure/llm_validity.py` | Batched heading validity via `LLMClient` |
| `src/structure/llm_toc.py` | TOC classification via LLM |
| `src/structure/toc_detection.py` | Orchestrates `llm_toc` + logging |
| `src/structure/heading_validation.py` | `llm_validate` + file writes |
| `src/structure/hierarchy.py` | Imports `LLMClient` (not used by current `run_pipeline`) |

**Indirect LLM coupling (fix without deleting the stage):**

- **`src/structure/toc_cleaning.py`** — imports `LLMClient` at top level, but **`clean_toc` is currently an identity** (`return list(headings)`). **`_llm_is_toc` is never called.** → Remove `LLMClient` import and dead `_llm_is_toc`, or replace module with a **5-line `identity_toc_clean.py`** until you need real cleaning again.

- **`src/generation/rewrite.py`** — uses `LLMClient` if that path runs; **CLI** sets generation engine to `None` in `command_loop`. Safe to **quarantine** with LLM folder if you drop generation.

**Config:** `src/config.py` still lists Gemini/LLM env vars — trim when LLM code is gone, or isolate in `config/llm.py` behind a feature flag (default off).

**Tools referencing LLM paths by filename only:**

- `tools/prompt_usage_report.py` — scans `src/LLMAdaptor/prompts`; **delete or rewrite** after adaptor removal.
- `tools/find_drop_reasons.py`, `tests/test_logging_contract.py` — reference **stage JSON names** like `04_llm_*.json`; update tests to **optional stages** or remove those filenames from the contract if you drop LLM artifacts entirely.

**Visualizer:** `visualizer.py` may **read** `05_llm_toc_classification.json` **if present** (optional layer). No hard dependency on `LLMAdaptor`.

---

## 3. Code not needed for `run_toc_trace` (under `src/`, excluding your excluded folders)

You asked to focus on redundancy **outside** `tools/`, `interaction/`, `ingestion/`, `export/` for “unnecessary” listings. Under **`src/`** these are **not** on the `run_pipeline` import tree:

| Path | Note |
|------|------|
| `src/LLMAdaptor/**` | LLM-only |
| `src/structure/llm_validity.py`, `llm_toc.py`, `toc_detection.py`, `heading_validation.py` | LLM pipelines |
| `src/structure/hierarchy.py` | LLM + not wired in `run_pipeline` |
| `src/structure/section_resolver.py` | Separate TOC-section resolver; not imported by `pipeline.py` |
| `src/structure/heading_candidates.py` | Unused + broken relative import |
| `src/core/candidate_scoring.py` | Duplicate of `structure/candidate_scoring` |
| `src/generation/**` | Not used by `run_toc_trace` |
| `src/interaction/**` | CLI (you excluded — keep for `main.py`) |
| `src/export/**` | Word export (excluded) |

**`src/ingestion/service.py`** — thin wrapper; **optional**; not required by `run_pipeline`.

**`scripts_generate_toc_split.py`**, root **`tmp_*.py`** — not part of the trace pipeline.

---

## 4. Target architecture: one “shell” pipeline + plugins

### 4.1 Principles

1. **Orchestrator** only: **load PDF → run ordered list of stage callables → optional persist → return `PipelineResult`**. No scoring rules, no regex, no continuity math in the shell.
2. **Each stage** is a **pure function** (or small class) with a **narrow contract**:  
   `(state: PipelineState) -> PipelineState` **or** explicit in/out dataclasses so micro-functions do not mutate unrelated data.
3. **Shared context** in one **`PipelineState`** (or `BookRunContext`): `lines`, `layout_payload`, `layout_by_line_id`, `candidates`, `headings`, `fragments_result`, `logger`, etc.
4. **`run_toc_trace`** only does: `from src.book_pipeline import run` (name TBD) + visualization + folder helpers.

### 4.2 Suggested package layout (rename as you prefer)

```
src/
  book_pipeline/                    # or keep src/core/pipeline as the public API
    __init__.py                     # export run_pipeline / run_book_pipeline
    runner.py                       # ONLY: stage list + loop + logging hooks + persist hook
    state.py                        # PipelineState dataclass
    stages/
      __init__.py
      extract.py                    # extract_pdf + normalize_text → lines
      layout_log.py                 # lines_to_log
      noise.py                      # mark_noise
      candidates.py                 # collect_candidates_scored
      heading_validity_gate.py      # gate_heading_validity_candidates (done)
      continuity.py                 # moved from inline loop in pipeline.py
      fragments.py                  # build_fragments
      toc_clean.py                  # clean_toc (identity or real)
      deterministic_toc.py          # detect_deterministic_toc, sections, book_metadata
      finalize_headings.py          # build dict rows + write final_headings + final_headings_2
    persistence/
      sqlite.py                     # optional: save book + toc + artifacts (current persist block)
  ingestion/                      # unchanged physically; imported by stages/extract.py
  structure/                      # gradually shrink: move used pieces under book_pipeline/stages
  debug/
    run_toc_trace.py              # calls book_pipeline.runner.run only
```

**Rename suggestions (remove “llm” from deterministic path):**

| Current | Suggested |
|---------|-----------|
| `pre_llm_gate.py` | **Renamed** to `heading_validity_gate.py`; stage `heading_validity_gate` → `03b_heading_validity_gate.json` |
| `toc_cleaning.py` (identity) | `toc_pass_through.py` or inline in runner until logic returns |

### 4.3 Plugin registration (sketch)

```python
# runner.py — no business rules
STAGES = [
    stage_extract,
    stage_layout_log,
    stage_noise,
    stage_candidates,
    stage_heading_gate,
    stage_continuity,
    stage_fragments,
    stage_toc_clean,
    stage_deterministic_toc_and_metadata,
    stage_write_final_json,
]

def run(pdf_path, *, enable_logs=False, persist_to_db=False):
    state = PipelineState(...)
    logger = make_logger(...)
    for fn in STAGES:
        state = fn(state, logger=logger)
    if persist_to_db:
        persist_sqlite(state, logger)
    return state.result, logger
```

Each `stage_*` lives in its own file so **changing continuity rules** never edits **fragment** code.

---

## 5. `tools/` folder after LLM removal

| Tool | Action |
|------|--------|
| `prompt_usage_report.py` | Remove or point to new prompt location if any |
| `run_pre_valid_gate_only.py` | Removed with `tools/`; use `heading_validity_gate` if reintroduced |
| `import_graph.py`, `find_unused_modules.py` | Re-run after restructure to validate orphans |
| Others | grep for `LLMAdaptor` / `llm_` and adjust paths |

---

## 6. Phased execution (low risk)

1. **Dead import cleanup:** Remove unused `LLMClient` import from `toc_cleaning.py`; delete unused `src/core/candidate_scoring.py` after confirming no dynamic import.
2. **Consolidate models:** Single `NormalizedLine` / heading types in one module; fix `pdf_extractor` import.
3. **Extract `continuity` block** from `pipeline.py` into `stages/continuity.py` — behavior unchanged, first real split.
4. **Introduce `PipelineState` + `runner.py`**; move one stage at a time.
5. **Move `src/LLMAdaptor` + LLM-only structure modules** to `archive/` or delete; fix tests and `tools/`.
6. ~~**Rename** `pre_llm_gate` / JSON stage names~~ — done (`heading_validity_gate`, `03b_heading_validity_gate.json`).

---

## 7. What stays excluded from “deletion” but should still be clear

- **`interaction/`**, **`export/`**, **`main.py`** — not used by `run_toc_trace`, but they are **other entry points**; keep behind a clear **`apps/cli/`** vs **`apps/trace/`** split if you want separation without deleting folders.

This plan matches your goals: **micro-functions** in stage modules, **one dumb pipeline**, **trace entry** only orchestrates, **LLM adaptor and dependents** removable, **duplicate / broken / duplicate scorer** identified, **tools** called out for follow-up edits.

---

## 8. Review: keeping `run_toc_trace` output the same (regression safety)

**Goal:** After any refactor, `python src/debug/run_toc_trace.py <same.pdf> [--visualize]` should produce **the same logical result** as today: same headings, same fragments, same deterministic TOC artifacts, same DB rows (for `persist_to_db=True`).

### 8.1 What “non-breaking” must preserve

| Invariant | Why it matters |
|-----------|----------------|
| **Public entry** | `run_toc_trace.run(pdf)` keeps calling **`run_pipeline`** (same module path or a thin re-export). Changing only internal layout is fine if the callable is identical. |
| **Stage order** | Same sequence: extract → normalize → layout log → noise → candidates → gate → continuity → fragments → `clean_toc` → deterministic TOC → final JSON writes → persist. Any reorder breaks parity. |
| **Logger stage keys → filenames** | `heading_validity_gate` → **`03b_heading_validity_gate.json`**. Older runs used `03b_pre_llm_heading_gate.json`. |
| **JSON envelope shape** | `PipelineLogger._envelope` fields (`run_id`, `stage`, `pdf_file`, `timestamp`, `total_items`, `items`) should stay stable for consumers. |
| **Algorithm identity** | Moving code into `stages/continuity.py` is safe **only if** logic is copied verbatim (same thresholds, same `re` patterns, same iteration order over `candidates`). |
| **`clean_toc`** | Today it returns `list(headings)` unchanged. Removing dead `LLMClient` / `_llm_is_toc` **without** changing `clean_toc`’s return path preserves behavior. |

### 8.2 Steps that can silently change results (extra care)

| Planned step | Risk |
|--------------|------|
| **Merge `NormalizedLine` / single types module (§6 phase 2)** | **Highest risk.** If construction of lines, defaults, or `normalize_text`’s list copy changes, **every downstream stage can change.** Mitigation: run a **golden PDF** before/after; **diff** `01_`–`12_` JSON (or hash stable subsets excluding `timestamp`/`run_id`). |
| **`PipelineState` vs in-place mutation** | If refactor switches from mutating shared lists to copying, you could change **object identity** only (usually OK) or accidentally **duplicate/miss** mutations (bug). Mitigation: keep one mutable `lines` / `headings` list through stages until you have tests. |
| **Rename JSON / stage names (§6 phase 6)** | **Not output-equivalent** for anyone comparing filenames. Defer until you accept a **v2 artifact layout**. |
| **Delete `src/core/candidate_scoring.py`** | **Low risk** if nothing imports it — no runtime change. |

### 8.3 What is safe without golden tests

- Deleting **`src/LLMAdaptor`** and LLM-only modules **not imported** by `run_pipeline` — **no change** to trace output (same transitive graph).
- Removing **unused top-level import** in `toc_cleaning.py` — **no change** to `clean_toc` output.
- **File moves** with **unchanged import graph** (e.g. `from src.structure.noise_filter import mark_noise` → same function object) — output unchanged.

### 8.4 Recommended verification (minimal)

1. Pick one **fixed PDF** used in CI or docs.
2. After each phase: run trace with `enable_logs=True`, compare **`09_final_headings.json`**, **`10_deterministic_toc.json`**, **`11_book_metadata.json`**, **`12_final_headings_2.json`** to a **saved baseline** (ignore `run_id`, `timestamp` in envelope if needed).
3. Run **`pytest tests/test_logging_contract.py`** if present — it encodes filename contracts.

**Conclusion:** The **architecture direction** in §4 does **not** require breaking behavior; **output parity** is preserved if you **keep algorithms and logger keys/filenames fixed** until an explicit “artifact v2” release. The riskiest item is **type consolidation** (§6.2) — do it only with before/after JSON diff, not as a drive-by edit.

# Pipeline Scripts Catalog

Scripts live under `backend/scripts/`. Run from repo root or `backend/`:

```bash
cd backend
python scripts/pipeline_full_book.py
```

**Canonical names** (preferred in docs and CI) delegate to **legacy names** (unchanged for existing automation).

---

## Primary workflows

| Canonical | Legacy | What it does |
|-----------|--------|--------------|
| `pipeline_full_book.py` | `run_full_openai_pipeline.py` | Full book: PDF → structure → parallel LLM rewrite → Markdown + DOCX. Applies `INGESTION_PROFILE` (default `fast_local`), single PDF extract, rewrite LLM cache. |
| `pipeline_signal_sections.py` | — (new, V2) | **Parallel PDF-mirror pipeline.** Preserves the source PDF's chapter / section hierarchy verbatim (no LLM renaming). One rewrite call per high-signal section via OpenRouter Gemini Flash Lite. Outputs `<title>__signal_<ts>.{md,docx}`; logs to `logs/run_signal_<ts>/`. Existing pipeline is untouched. See `SIGNAL_*` env vars and [`specs/modules/pipeline-signal-sections.md`](../../specs/modules/pipeline-signal-sections.md). |
| `export_notes_docx.py` | `reexport_docx.py` | Rebuild Markdown + DOCX from saved `logs/run_*` + `rewritten_map` sidecar — no structure or rewrite. |
| `audit_notes_quality.py` | `run_notes_quality_audit.py` | Post-export quality audit (deterministic checks + optional LLM insights). |
| `pipeline_batch_books.py` | `run_batch_pipeline.py` | Run full pipeline + audit for multiple PDFs; writes comparison under `output/batch/`. |

### Key environment variables (full pipeline)

| Variable | Purpose |
|----------|---------|
| `PIPELINE_PDF` | Source PDF path |
| `REWRITE_USER_INSTRUCTION` | How sections should be rewritten |
| `INGESTION_PROFILE` | `fast_local` \| `quality_cloud` \| `debug` |
| `SKIP_STRUCTURE` | `1` + `PIPELINE_LOG_DIR` → rewrite-only from saved logs |
| `NOTES_QUALITY_LLM` | `0` to skip LLM in quality audit |

### Key environment variables (signal-sections pipeline V2)

| Variable | Purpose |
|----------|---------|
| `PIPELINE_PDF` | Source PDF path (shared with the full pipeline) |
| `SIGNAL_BOUNDARY_PERCENTILE` | Top-N % of validated headings to keep as section boundaries (default `35`) |
| `SIGNAL_BOUNDARY_MIN_SCORE` | Minimum raw heading score required (default `6`) |
| `SIGNAL_BOUNDARY_INCLUDE_STRUCTURAL` | `1` keeps universal `CHAPTER/MODULE/UNIT/PART N` markers regardless of score |
| `SIGNAL_PROMOTE_H1_COUNT` | Fallback L1 promotions when no structural markers exist (default `8`) |
| `SIGNAL_REWRITE_PROVIDER` | `openrouter` (default) |
| `SIGNAL_REWRITE_MODEL` | OpenRouter slug (default `google/gemini-2.5-flash-lite-preview`) |
| `SIGNAL_REWRITE_MAX_TOKENS` | Per-section completion ceiling (default `2500`) |
| `SIGNAL_REWRITE_OVERLAP_CHARS` | Tail+head chars used as prev/next continuity context (default `600`) |
| `SIGNAL_REWRITE_PARALLEL_WORKERS` | Concurrent LLM calls (default `4`) |
| `SIGNAL_REWRITE_USER_INSTRUCTION` | Style override; falls back to `REWRITE_USER_INSTRUCTION` |
| `SIGNAL_OUTPUT_SUFFIX` | Output filename suffix (default `__signal`) |
| `SIGNAL_EXPORT_DOCX` | `0` to write only Markdown |

---

## Structure iteration (saved logs)

| Script | What it does |
|--------|--------------|
| `run_heading_stages.py` | Re-run structure title/chapter phases (15f–15j) on an existing `logs/run_*` folder. |
| `run_15f_cleanup.py` | Run 15f heading cleanup only (needs 15e artifact). |
| `run_15e_test.py` | Dev harness for 15e chapter grouping (+ optional sample rewrite). |
| `run_15g_validation.py` | Run 15g title validation on saved hierarchy. |
| `bench_15f_cleanup.py` | Benchmark 15f modes (rules vs MiniLM vs cloud). |
| `run_upgrade_validation.py` | Smoke: `fast_local` structure + sample rewrite; prints artifact paths. |

---

## Recovery & partial runs

| Script | What it does |
|--------|--------------|
| `rewrite_missing_sections.py` | Fill gaps in `rewritten_map`, merge into MD, validate, export DOCX. |
| `build_rewritten_sidecar.py` | Build `rewritten_map` JSON from an existing Markdown file. |
| `export_universal_docx.py` | Convert a `.md` file to DOCX with theme env vars (no pipeline). |

---

## Audit & comparison

| Script | What it does |
|--------|--------------|
| `compare_notes_quality.py` | Diff quality audit reports across runs. |
| `compare_runs.py` | Summarize metadata from multiple `logs/run_*` folders. |
| `audit_headings.py` | Heading-quality checks on hierarchy JSON (e.g. 15j). |
| `audit_section_topics.py` | Section topic classification vs PDF source. |

---

## Integration & maintenance

| Script | What it does |
|--------|--------------|
| `run_e2e_scenarios.py` | Rewrite + Q&A integration smoke on configured books. |
| `migrate_runtime_to_root.py` | One-time move of logs/output to repo-root layout. |

---

## Stage naming

Pipeline **function names** and **UI progress** use semantic IDs from `stage_catalog.py` (e.g. `stage_ingest_pdf`, `stage_build_book_structure`). **Log artifact keys and filenames** (`s01_…`, `s15a_…`) are unchanged for backward compatibility.

Authoritative human-readable map: [specs/modules/stage-catalog.md](../../specs/modules/stage-catalog.md).

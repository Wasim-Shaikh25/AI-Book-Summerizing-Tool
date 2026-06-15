# Module: Logging & Debug

> **Code:** `backend/src/modules/structure/logging/`, `backend/src/modules/debug/`  
> **Stage name map:** [stage-catalog.md](./stage-catalog.md)

---

## 1. Purpose

Whitelisted stage JSON logging and PDF visualization for pipeline debugging.

---

## 2. PipelineLogger

**File:** `backend/src/modules/structure/logging/pipeline_logger.py`

```python
class PipelineLogger:
    @classmethod
    def create(cls, *, pdf_file: str, enabled: bool) -> PipelineLogger | NoOpPipelineLogger: ...

    def write_stage(self, stage_name: str, payload) -> None: ...
    def write_stage_payload(self, stage_name: str, payload) -> None: ...
```

- Writes to `{PROJECT_ROOT}/logs/run_<utc>/` when `enable_logs=True` (`LOGS_FOLDER` in config)
- Whitelisted stage filenames only (enforced in logger)
- `NoOpPipelineLogger` used when logging disabled (zero overhead)
- JSON envelope field `"stage"` uses **semantic log keys** (e.g. `group_chapters`, not `15e_chapter_hierarchy`)

---

## 3. Expected Log Artifacts

Written by `backend/src/modules/pipeline/stages.py` and `structure_orchestrator.py`:

| Log file | Log key (semantic) | Stage function |
|----------|-------------------|----------------|
| `s00_document_profile.json` | `document_profile` | `stage_compute_document_profile` |
| `s01_layout_lines.json` | `layout_lines` | `stage_log_layout` |
| `s02_noise_filter.json` | `noise_filter` | `stage_filter_noise` |
| `s03_candidate_scoring.json` | `candidate_scoring` | `stage_score_heading_candidates` |
| `s04_heading_validity_gate.json` | `heading_validity_gate` | `stage_gate_heading_candidates` |
| `s05_fragments.json` | `fragments` | `stage_build_fragments` |
| `s06_continuity_filter.json` | `continuity_filter` | `stage_filter_continuity` |
| `s07_final_headings.json` | `final_headings` | `stage_finalize_heading_list` |
| `s08_deterministic_toc.json` | `deterministic_toc` | `stage_finalize_heading_list` |
| `s09_book_metadata.json` | `book_metadata` | `stage_finalize_heading_list` |
| `s10_final_headings_2.json` | `final_headings_2` | `stage_finalize_heading_list` |
| `s11_visual_elements.json` | `visual_elements` | `stage_log_layout` |
| `s12_doubted_sections.json` | `doubted_sections` | `stage_flag_doubted_toc` |
| `s15b_doubted_resolved.json` | `resolve_doubted_toc` | `stage_resolve_doubted_toc` |
| `s15b_revalidation.json` | `resolve_doubted_revalidation` | `stage_resolve_doubted_toc` |
| `s15a_heading_hierarchy.json` | `partition_tree` | `stage_build_book_structure` |
| `s15d_ultimate_sections.json` | `partition_sections` | `stage_build_book_structure` |
| `s15e_chapter_hierarchy.json` | `group_chapters` | `stage_build_book_structure` |
| `s15f_heading_cleanup.json` | `clean_titles` | `stage_build_book_structure` |
| `s15h_chapter_placement.json` | `place_chapters` | `stage_build_book_structure` |
| `s15i_heading_refinement.json` | `refine_titles` | `stage_build_book_structure` |
| `s15j_hierarchy_openai.json` | `cloud_hierarchy` | `stage_build_book_structure` |
| `s15g_title_validation.json` | `validate_titles` | `stage_build_book_structure` |
| `s15c_final_book.json` | `assemble_book` | `stage_build_book_structure` |
| `s16_rag_snapshot.json` | `rag_snapshot` | `stage_build_book_structure` |

Authoritative mapping: `backend/src/modules/pipeline/stage_registry.py`.  
Legacy log keys (`15e_chapter_hierarchy`, …) and legacy filenames (`01_`, `15d_` without `s`) are read-compatible via `normalize_log_key()` / `resolve_existing_artifact()`.

---

## 4. Debug Tools

| Tool | Entry | Behavior |
|------|-------|----------|
| TOC trace | `python -m src.modules.debug.run_toc_trace <pdf>` | Pipeline with logs + DB persist |
| Visualizer | `visualize_run(pdf_path, run_dir)` | Annotated debug PDF from stage JSON |

**Files:**
- `backend/src/modules/debug/run_toc_trace.py`
- `backend/src/modules/debug/visualizer.py`

---

## 5. Dependencies

See [pipeline-core.md](./pipeline-core.md), [structure-extraction.md](./structure-extraction.md).

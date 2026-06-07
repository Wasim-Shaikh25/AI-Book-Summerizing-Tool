# Module: Logging & Debug

> **Code:** `backend/src/modules/structure/logging/`, `backend/src/modules/debug/`

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
    def write_stage_payload(self, filename: str, payload) -> None: ...
```

- Writes to `logs/run_<utc>/` when `enable_logs=True`
- Whitelisted stage filenames only (enforced in logger)
- `NoOpPipelineLogger` used when logging disabled (zero overhead)

---

## 3. Expected Log Artifacts

Written by `backend/src/modules/pipeline/stages.py`:

| Log file | Stage |
|----------|-------|
| `01_layout_lines.json` | `stage_layout_log` |
| `02_noise_filter.json` | `stage_noise` |
| `03_candidate_scoring.json` | `stage_candidates` |
| `03b_heading_validity_gate.json` | `stage_heading_gate` |
| `07_fragments.json` | `stage_fragments` |
| `08b_continuity_filter.json` | `stage_continuity` |
| `09_final_headings.json` | `stage_finalize_headings` |
| `10_deterministic_toc.json` | `stage_finalize_headings` |
| `11_book_metadata.json` | `stage_finalize_headings` |
| `12_final_headings_2.json` | `stage_finalize_headings` |
| `13_visual_elements.json` | `stage_layout_log` |
| `14_doubted_sections.json` | `stage_doubted_sections` |
| `15b_doubted_resolved.json` | `stage_15b_resolver` |
| `15b_revalidation.json` | `stage_15b_resolver` |
| `15a_heading_hierarchy.json` | `stage_final_structuring` |
| `15d_ultimate_sections.json` | `stage_final_structuring` |
| `15e_chapter_hierarchy.json` | `stage_final_structuring` |
| `15f_heading_cleanup.json` | `stage_final_structuring` |
| `15c_final_book.json` | `stage_final_structuring` |
| `16_rag_snapshot.json` | `stage_final_structuring` |

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

- Stage payloads from `run_pipeline(enable_logs=True)`
- PyMuPDF for visualization overlay

---

## 6. Tests

| Test | Coverage |
|------|----------|
| `test_logging_contract.py` | All expected stage JSON files exist with valid schema |

See [testing.md](../testing.md) §6.1.

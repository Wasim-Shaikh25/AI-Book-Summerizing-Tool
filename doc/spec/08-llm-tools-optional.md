# 08 — Generation, tests

## LLM stack (removed)

The in-repo **`src/LLMAdaptor`** package and LLM-driven structure modules (`llm_validity`, `llm_toc`, `toc_detection`, LLM `heading_validation`, `hierarchy`, `section_resolver`, `heading_candidates`) have been **removed**. The deterministic pipeline does not depend on them.

Legacy **stage JSON filenames** such as `04_llm_heading_validation.json` may still appear in `PipelineLogger` allowlists for optional artifacts from older runs; `run_pipeline` does not produce those stages today.

## Generation / rewrite

**File:** `src/generation/rewrite.py` — `RewriteEngine` is a **stub** (`NotImplementedError` on use).  
**Status:** `CommandLoop` sets `ContentGenerationEngine = None`; ingestion uses `run_pipeline` only.

## Export

**File:** `src/export/word_exporter.py` — Word export from structured text.  
**File:** `src/export/output_manager.py` — `OutputManager` helper.

## Tests

**Directory:** `tests/`

- `test_logging_contract.py` — logger contract (integration; `RUN_INTEGRATION=1`)
- `test_fragment_coverage.py` — fragments (integration)
- `test_heading_validator_heuristics.py` — enumerated-list heuristic

## Scratch files

Avoid committing ad-hoc `tmp_*.py` at repo root.

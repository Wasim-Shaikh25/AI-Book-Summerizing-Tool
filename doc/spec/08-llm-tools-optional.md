# 08 — Generation, tests

## LLM stack

Legacy **`src/LLMAdaptor`** and LLM-driven structure stages (`llm_validity`, `llm_toc`, etc.) are **removed**.

**Stage 15b:** Fast deterministic pass on all doubted segments, then **selective revalidation** via a small local model (`DOUBTED_RESOLVER_MODE=revalidate_selected`).

- Fast models (Ollama / llama.cpp): `qwen2.5:0.5b-instruct`, `qwen2.5:1.5b-instruct`, `llama3.2:1b-instruct`
- Env (fast default): `DOUBTED_RESOLVER_LLM=llamacpp`, `LLAMACPP_MODEL_PATH=...gguf`
- Ollama alternative: `DOUBTED_RESOLVER_LLM=ollama`, `DOUBTED_REVALIDATION_MODEL=qwen2.5:0.5b-instruct`
- Logs: `15b_doubted_resolved.json`, `15b_revalidation.json`
- BigBird (`DOUBTED_RESOLVER_LLM=bigbird`) is legacy and slow; not recommended.

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

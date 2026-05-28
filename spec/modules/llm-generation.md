# Module: LLM & Generation

> Code: `src/modules/generation/`, `src/modules/pipeline/llm_chat_client.py`

## Purpose

Optional LLM overlays: doubted-section resolver (Stage 15b), rewrite/content generation.

## Components

| Component | Status | Module |
|-----------|--------|--------|
| `LlmChatClient` | Active | `pipeline/llm_chat_client.py` |
| `RewriteModelRouter` | Active | `generation/model_router.py` |
| `RewriteEngine` | Active | `generation/rewrite.py` |
| `FastSegmentLlm` | Active | `structure/final_structuring/models/segment_llm_classifier.py` |
| Doubted resolver | Active | `structure/final_structuring/doubted_section_resolver.py` |
| Revalidation | Active | `structure/final_structuring/revalidation.py` |
| Signal extractors | Active | `final_structuring/signal_extractor.py`, encoder models |

## Stage 15b

Runs when `first_toc_page > 3` (late TOC). Pipeline stage: `stage_15b_resolver` in `stages.py`.

Env keys: see `parameters-config.md` § Doubted resolver.

Logs: `15b_doubted_resolved.json`, `15b_revalidation.json`

## Rewrite

Post-ingestion via CLI or `scripts/run_full_openai_pipeline.py`. Uses persisted TOC from SQLite.

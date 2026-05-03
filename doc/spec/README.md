# Project specs (method / call-chain index)

This folder documents the **AI Notes Creator / Book Summarizing** codebase as **call chains**: who calls whom, in what order, for each major flow.

Read order:

| File | Topic |
|------|--------|
| [00-overview.md](00-overview.md) | Packages, entry points, data shapes |
| [01-entry-cli-interaction.md](01-entry-cli-interaction.md) | `main.py` → `CommandLoop` → ingestion / intents |
| [02-pipeline-core-chain.md](02-pipeline-core-chain.md) | `run_pipeline` stage order (production path) |
| [03-ingestion-layer.md](03-ingestion-layer.md) | PDF extract → normalize → layout JSON |
| [04-structure-extraction-chain.md](04-structure-extraction-chain.md) | Noise → candidates → gate → continuity → fragments → TOC clean |
| [05-deterministic-toc-persistence.md](05-deterministic-toc-persistence.md) | Repeat-TOC, metadata, DB artifact save |
| [06-logging-debug-visualization.md](06-logging-debug-visualization.md) | `PipelineLogger`, `run_toc_trace`, `visualizer` |
| [07-storage-repositories.md](07-storage-repositories.md) | `KnowledgeStore`, book/TOC persistence |
| [08-llm-tools-optional.md](08-llm-tools-optional.md) | Generation stub, tests (LLM stack removed) |
| [RESTRUCTURE-PLAN.md](RESTRUCTURE-PLAN.md) | Plugin-style pipeline proposal, trace dependency closure, LLM removal, dead files |

Cross-cutting types live in `src/core/models.py` and `src/domain/document.py` (overlapping dataclasses used by pipeline and storage).

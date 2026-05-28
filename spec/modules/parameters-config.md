# Module: Parameters & Config

> Code: `config/default.yaml`, `src/shared/config.py`, `.env.example`  
> MESO Rule 12: tunables belong here, not as literals in business logic.

## Purpose

Central configuration for paths, chunking, LLM providers, and rewrite/doubted-resolver tuning.

Runtime loader: **`src/shared/config.py`** reads `config/default.yaml` then overlays environment variables and `.env`.

## Path Constants (derived from config + repo root)

| YAML key | Env override | Purpose |
|----------|--------------|---------|
| `paths.pdf_folder` | — | Input PDFs |
| `paths.output_folder` | — | Generated docx |
| `paths.reference_docx` | — | Pandoc reference |
| `paths.models_dir` | — | Local GGUF weights |

## Chunking

| Key | Default |
|-----|---------|
| `CHUNK_SIZE_WORDS` | 1500 |
| `CHUNK_OVERLAP_WORDS` | 150 |

## LLM Provider

| Key | Source | Notes |
|-----|--------|-------|
| `LLM_PROVIDER` | env / `.env` | `LLAMACPP`, `OLLAMA`, `OPENAI`, `GEMINI` |
| `LLM_MODEL` | env | Provider-specific model id |
| `LLM_BASE_URL` | env | API base for remote providers |
| `LLM_TIMEOUT_S` | env | Request timeout |
| Provider keys | env | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_*`, `LLAMACPP_*` |

## Rewrite / Doubted Resolver

| Key | Purpose |
|-----|---------|
| `REWRITE_*` | Rewrite batch sizing and limits |
| `DOUBTED_*` | Stage 15b resolver mode and model paths |
| `FULL_REWRITE_MAX_CHUNKS` | Cap on rewrite chunks |

## Debug

| Key | Default |
|-----|---------|
| `DEBUG_STRUCTURE` | `True` |

## Policy

New tunables MUST be added to this spec and `.env.example` before use in code.

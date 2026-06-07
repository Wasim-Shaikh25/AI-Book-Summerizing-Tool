# Module: Parameters & Config

> **Role:** Authoritative for all env vars and YAML config (MESO Rule 12).  
> **Code:** `backend/config/default.yaml`, `backend/src/shared/config.py`, `backend/auth/config.py`, `.env.example`

---

## 1. Purpose

Central configuration for paths, chunking, LLM providers, rewrite/doubted-resolver tuning, RAG, OCR, and web platform settings.

**Loader:** `backend/src/shared/config.py` reads `backend/config/default.yaml`, then overlays environment variables and repo-root `.env`.

---

## 2. Path Constants

| YAML key | Resolved path | Purpose |
|----------|---------------|---------|
| `paths.pdf_folder` | `{PROJECT_ROOT}/pdfs` | Input PDFs |
| `paths.output_folder` | `{PROJECT_ROOT}/output` | Generated docx, DB |
| `paths.reference_docx` | `{PROJECT_ROOT}/reference.docx` | Pandoc reference |
| `paths.models_dir` | `{PROJECT_ROOT}/models` | Local GGUF weights |
| `RAG_INDEX_DIR` | `{PROJECT_ROOT}/output/rag_index` | FAISS indexes |

`PROJECT_ROOT` defaults to parent of `backend/`; override via env for Docker (`/workspace`).

---

## 3. Chunking

| Key | Default |
|-----|---------|
| `CHUNK_SIZE_WORDS` | 1500 |
| `CHUNK_OVERLAP_WORDS` | 150 |

---

## 4. LLM Provider

| Key | Source | Notes |
|-----|--------|-------|
| `LLM_PROVIDER` | env | `LLAMACPP`, `OLLAMA`, `OPENAI`, `GEMINI` |
| `LLM_MODEL` | env | Provider-specific model id |
| `LLM_BASE_URL` | env | API base for remote providers |
| `LLM_TIMEOUT_S` | env | Request timeout (default 600) |
| `OPENAI_API_KEY`, `GEMINI_API_KEY` | env | Provider secrets |
| `LLAMACPP_MODEL_PATH`, `REWRITE_LLAMACPP_MODEL_PATH` | env | Local GGUF paths |
| `REWRITE_PROVIDER_ORDER` | env | e.g. `openai,gemini,llamacpp` |

---

## 5. Rewrite & Doubted Resolver

| Key | Purpose |
|-----|---------|
| `REWRITE_MAX_TOKENS` | Max tokens per rewrite chunk |
| `REWRITE_PARALLEL_WORKERS` | Parallel section rewrite threads |
| `REWRITE_CONTEXT_OVERLAP_CHARS` | Context overlap between sections |
| `REWRITE_AUTO_RETRY_MISSING` | Auto-retry missing sections |
| `FULL_REWRITE_MAX_CHUNKS` | Cap on rewrite chunks (0 = unlimited) |
| `DOUBTED_RESOLVER_MODE` | `fast` \| `revalidate_selected` |
| `DOUBTED_RESOLVER_LLM` | `off` \| `ollama` \| `llamacpp` \| `bigbird` |
| `CHAPTER_HIERARCHY_*` | Stage 15e LLM config |
| `HEADING_CLEANUP_*` | Stage 15f LLM config |
| `ULTIMATE_*` / `ULTIMATE_PROFILE` | Stage 15d section sizing |

---

## 6. Vector RAG

| Key | Default | Purpose |
|-----|---------|---------|
| `RAG_ENABLED` | true | Enable FAISS hybrid retrieval |
| `RAG_TOP_K` | 6 | Retrieved chunks per question |
| `RAG_VECTOR_WEIGHT` | 0.65 | Semantic weight |
| `RAG_LEXICAL_WEIGHT` | 0.35 | Keyword weight |
| `RAG_CHUNK_SIZE_WORDS` | 0 | 0 = one chunk per section |
| `UPLOAD_SKIP_RAG` | true | Skip index build on web upload |

---

## 7. Page OCR

| Key | Default | Purpose |
|-----|---------|---------|
| `OCR_ENABLED` | true | Master switch |
| `OCR_MODE` | auto | `auto` \| `force` \| `off` |
| `OCR_SPLIT_TWO_UP` | false | Split page at 50% for two-up scans |
| `OCR_MIN_TEXT_CHARS` | 40 | Below this → treat as scan |
| `OCR_ZOOM` | 2.0 | Tesseract render scale |
| `OCR_LANG` | eng | Tesseract language |
| `TESSERACT_CMD` | — | Path to tesseract binary (Windows) |

See [requirements-ocr-stage.md](../requirements-ocr-stage.md).

---

## 8. Web Platform (`backend/auth/config.py`)

| Key | Default | Purpose |
|-----|---------|---------|
| `AUTH_ENABLED` | true | `false` = guest dev mode |
| `JWT_SECRET` | dev default | HS256 signing key |
| `JWT_EXPIRE_DAYS` | 7 | Token lifetime |
| `FRONTEND_URL` | `http://localhost:5173` | OAuth redirect |
| `MAX_UPLOAD_MB` | 100 | PDF upload size cap |
| `CHAT_DOCX_CHAR_LIMIT` | 4000 | Auto Word export threshold |
| `RATE_LIMIT_REQUESTS` | 60 | Per-IP request cap |
| `RATE_LIMIT_WINDOW_SECONDS` | 60 | Rate limit window |

---

## 9. Debug

| Key | Default |
|-----|---------|
| `DEBUG_STRUCTURE` | true |
| `PIPELINE_MAX_PAGES` | 0 (all pages) |

---

## 10. Policy

New tunables MUST be added in this order:

1. This spec
2. `backend/config/default.yaml` or `backend/auth/config.py`
3. `.env.example`
4. Code (read via config, never hardcode)

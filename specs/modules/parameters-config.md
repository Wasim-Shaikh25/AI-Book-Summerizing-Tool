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
| `paths.output_folder` | `{PROJECT_ROOT}/output` | DB, exports, uploads, RAG indexes |
| `paths.logs_folder` | `{PROJECT_ROOT}/logs` | Pipeline stage JSON (`run_<utc>/`) |
| `KNOWLEDGE_DB_PATH` | `{OUTPUT_FOLDER}/knowledge_base.db` | SQLite (engine + platform) |
| `EXPORTS_FOLDER` | `{OUTPUT_FOLDER}/exports` | Web Word exports |
| `UPLOADS_FOLDER` | `{OUTPUT_FOLDER}/uploads` | Uploaded PDFs |
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
| `REWRITE_AUTO_RETRY_ENABLED` | Inline retry after parallel rewrite |
| `REWRITE_AUTO_RETRY_MAX_PASSES` | Max inline retry passes (default 1) |
| `REWRITE_AUTO_RETRY_MIN_COVERAGE` | Retry when coverage below this (default 0.95) |
| `REWRITE_AUTO_RETRY_MISSING` | Legacy alias for auto-retry enable |
| `REWRITE_BUNDLE_SIZE` | Sections per LLM call (default 1) |
| `FULL_REWRITE_MAX_CHUNKS` | Cap on rewrite chunks (0 = unlimited) |
| `DOUBTED_RESOLVER_MODE` | `fast` \| `revalidate_selected` |
| `DOUBTED_RESOLVER_LLM` | `off` \| `ollama` \| `llamacpp` \| `bigbird` |
| `CHAPTER_HIERARCHY_*` | `group_chapters` stage LLM config |
| `HEADING_CLEANUP_*` | `clean_titles` stage LLM config |
| `ULTIMATE_*` / `ULTIMATE_PROFILE` | `partition_sections` section sizing |
| `REWRITE_FIDELITY_MIN_OVERLAP` | Regenerate rewrite when source overlap below this (default 0.30) |
| `REWRITE_FIDELITY_REGENERATE_TEMPERATURE` | Reserved for future provider-specific retry temperature |
| `REWRITE_MIN_GROUNDING_CHARS` | Min real (non-list) source chars for a section to count as groundable prose (default 160) |
| `EXPORT_MISSING_BODY_MODE` | `placeholder` \| `fail` \| `skip` when rewrite body empty |
| `NOTES_STRUCTURE_FIX_ENABLED` | Run post-export structural cleanup in full pipeline (default true) |
| `NOTES_STRUCTURE_FIX_ENGINE` | `hybrid` \| `minilm` \| `api` — heading repair engine |
| `NOTES_STRUCTURE_FIX_MERGE_DUPLICATES` | Merge near-identical adjacent sections (default false) |
| `NOTES_STRUCTURE_FIX_DROP_LOW_GROUNDING` | Drop index/contents-style sections when log dir available (default false) |

### Structure grounding (upstream low-grounding fix)

| Key | Default | Purpose |
|-----|---------|---------|
| `PARTITION_DROP_LOW_GROUNDING` | `true` | `partition_sections` skips emitting a section whose reconstructed body is an index/contents listing (enumeration-dominated or < 40 real chars). YAML: `structure.partition_drop_low_grounding` |
| `CONTENTS_REGION_DETECTION` | `true` | `detect_toc` flags mid-document pages dominated by enumerated title rows (≥ 5 rows, ≥ 50 %) so their headings are excluded from partitioning. YAML: `structure.contents_region_detection` |

---

## 5a. Document profile (measured)

| Key | Default | Purpose |
|-----|---------|---------|
| `DOCUMENT_PROFILE_SHORT_BODY_CHARS` | 400 | Threshold for short-section ratio |
| `DOCUMENT_PROFILE_BASE_MIN_SECTION_BODY_CHARS` | 200 | Base min body for `partition_sections` |
| `DOCUMENT_PROFILE_BASE_REWRITE_OVERLAP_CHARS` | 600 | Base neighbour context for rewrite |
| `DOCUMENT_PROFILE_BASE_REWRITE_MAX_TOKENS` | 1800 | Base output token budget |
| `DOCUMENT_PROFILE_BASE_MEDIAN_SECTION_BODY_CHARS` | 1200 | Normalizer for token scaling |

YAML block: `document_profile:` in `default.yaml`.

---

## 5b. Chapter placement & title validation

| Key | Default | Purpose |
|-----|---------|---------|
| `CHAPTER_PLACEMENT_ENABLED` | true | Run `place_chapters` |
| `CHAPTER_PLACEMENT_MAX_SECTIONS_PER_CHAPTER` | 10 | Split trigger for `enforce_chapter_structure` |
| `CHAPTER_PLACEMENT_MIN_SECTIONS_PER_CHAPTER` | — | Merge undersized chapters |
| `CHAPTER_PLACEMENT_REASSIGN` | true | Move outlier sections by page cohesion |
| `CHAPTER_PLACEMENT_RENAME_CHAPTERS` | true | Refine generic chapter titles |
| `CHAPTER_PLACEMENT_COHESION_THRESHOLD` | — | MiniLM cohesion for reassignment |
| `TITLE_VALIDATION_ENABLED` | true | Run `validate_titles` after `cloud_hierarchy` |
| `HIERARCHY_OPENAI_ENABLED` | false | Master switch for `cloud_hierarchy` cloud passes |
| `HIERARCHY_OPENAI_AUTO_SKIP` | true | Skip `cloud_hierarchy` when local hierarchy sufficient |
| `HIERARCHY_OPENAI_*` | — | Regroup batch size, target chapters, provider |

**fast_local profile** also sets: `DOUBTED_RESOLVER_LLM=off`, `USE_LLM_INTENT=false`, `NOTES_QUALITY_LLM=false`, `HEADING_REFINEMENT_OPENAI_FALLBACK=false`.

---

## 5c. Notes quality audit

Read directly from env in `quality/` (not yet in `shared/config.py`):

| Key | Default | Purpose |
|-----|---------|---------|
| `NOTES_QUALITY_AUDIT` | `1` | Run after pipeline export |
| `NOTES_QUALITY_LLM` | `1` | LLM insights section |
| `NOTES_QUALITY_LINE_AUDIT` | `1` | Line-by-line scan |
| `NOTES_QUALITY_LINE_AUDIT_STRICT` | `0` | Stricter line thresholds |
| `NOTES_QUALITY_SEMANTIC_GROUNDING` | `1` | Re-check `low_source_overlap` lines with MiniLM; accept semantically grounded paraphrase, still flag real drift |
| `NOTES_QUALITY_SEMANTIC_MIN_SIM` | `0.45` | Min MiniLM cosine similarity for a paraphrased line to count as grounded |
| `NOTES_QUALITY_PDF_MATCH_SOURCE_GROUNDING` | `1` | Accept clean (looks_ok) titles not verbatim in the PDF when ≥60% of title words are covered by the section source (`grounded_in_source`) |
| `NOTES_QUALITY_LLM_PROVIDER` | empty | Override `LLM_PROVIDER` |
| `NOTES_QUALITY_OUT_DIR` | empty | Report output directory |

See [quality.md](./quality.md).

---

## 5d. Ingestion profile

| Key | Default | Purpose |
|-----|---------|---------|
| `INGESTION_PROFILE` | `fast_local` | `fast_local` \| `quality_cloud` \| `debug` |

Profile overrides: `ingestion/profile.py` — see [code-reference/ingestion.md](../code-reference/ingestion.md).

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
| `AUTH_ENABLED` | true | `false` = shared dev identity (no login) |
| `ALLOW_GUEST` | true | Offer "Continue as guest"; when auth enabled, mints isolated guest + JWT |
| `JWT_SECRET` | dev default | HS256 signing key — **set random in prod** |
| `JWT_EXPIRE_DAYS` | 7 | Token lifetime |
| `FRONTEND_URL` | `http://localhost:5173` | OAuth redirect + CORS origin |
| `CORS_EXTRA_ORIGINS` | `""` | Comma-separated extra allowed CORS origins (`AuthSettings.cors_origins`) |
| `UVICORN_WORKERS` | 1 | Worker processes (prod compose default 2) |
| `MAX_UPLOAD_MB` | 100 | PDF upload size cap |
| `CHAT_DOCX_CHAR_LIMIT` | 4000 | Auto Word export threshold |
| `RATE_LIMIT_REQUESTS` | 60 | Per-IP request cap |
| `RATE_LIMIT_WINDOW_SECONDS` | 60 | Rate limit window |

---

## 8a. LLM Cost & Robustness (`backend/src/shared/config.py`, `llm_cache.py`)

| Key | Default | Purpose |
|-----|---------|---------|
| `OPENAI_MAX_RETRIES` | 2 | Bounded retries on transient OpenAI errors (429/5xx/timeout); 4xx falls through to model fallback |
| `OPENAI_RETRY_BACKOFF_S` | 1.5 | Exponential backoff base (seconds) between retries |
| `REWRITE_CACHE_ENABLED` | true | Disk content-hash cache of rewrite completions (set `0` to disable; skips identical LLM calls across re-runs) |
| `LLM_CACHE_DIR` | `output/.llm_cache` | Cache location (keyed by model namespace + prompt hash + max_tokens) |

> Stage `cloud_hierarchy` (`hierarchy_openai_refinement`) additionally **skips** the OpenAI
> names pass when all hierarchy titles are already clean
> (`_hierarchy_titles_need_cloud_cleanup`), reducing API calls on well-structured docs.

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

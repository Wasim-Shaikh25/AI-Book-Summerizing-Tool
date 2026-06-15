# Change Plan — Local Ingestion, Performance & Structure Hardening

> **Role:** Master execution plan from agent workflow discussions (2026-06-07).  
> **Status:** **Complete** — all phases implemented (Phase 7 as import shims, not file moves).  
> **Related:** [tasks.md](./tasks.md) · [`../specs/index.md`](../specs/index.md)

---

## 1. Executive Summary

| Problem | Status |
|---------|--------|
| UI ingestion slow | **Done** — single extract, `fast_local` profile, lazy RAG, OCR 1.5 |
| Code scattered / irregular logs | **Done** — `stage_registry`, canonical `s01`–`s16`, `LOGS_FOLDER` |
| Mixed model story on upload | **Done** — BigBird 15b/15e, FLAN 15f via profile |
| Q&A retrieval gaps | **Done** — cross-encoder rerank + context builder |
| Wrong log location | **Done** — `{PROJECT_ROOT}/logs` |

**Default upload profile:** `fast_local` (CPU structure, lazy RAG, FLAN 15f).

---

## 2. Implementation Checklist (all phases)

### Phase 0 — Performance ✅
- [x] Fix double `extract_pdf`
- [x] `stage_registry.py` + `s01`–`s16` filenames
- [x] `LOGS_FOLDER` / path constants
- [x] `ingestion.profile` (`profile.py` + `default.yaml`)
- [x] Lazy RAG on first ask
- [x] Per-stage upload progress (registry + API `stage`/`percent`)
- [x] OCR zoom 1.5 for `fast_local`

### Phase 1 — Local structure ✅
- [x] 15b BigBird + fast mode via profile
- [x] 15e rules + BigBird via profile
- [x] Wired in `IngestionService`

### Phase 2 — FLAN-T5 15f ✅
- [x] `flan_title_cleaner.py` + `mini_lm_title_pick.py`
- [x] `HEADING_CLEANUP_BACKEND=flan`
- [x] `scripts/bench_15f_cleanup.py`

### Phase 3–4 — RAG ✅
- [x] `rag/reranker.py` — cross-encoder rerank top 50 → 6–8
- [x] `rag/context_builder.py` — dedupe, budget, citations
- [x] Wired in `retriever.py`, `RagService`, `BookQaEngine`
- [x] Config: `RAG_RERANK_*`, `RAG_CONTEXT_MAX_CHARS`

### Phase 5 — Registry ✅
- [x] `stage_registry.py` single source
- [x] `STAGES = get_pipeline_stages()` from registry
- [x] `PIPELINE_STAGE_PROGRESS` aligned with stage functions

### Phase 6 — Structure ✅
- [x] PDF bookmark TOC fallback — `ingestion/pdf_outline.py` + `stage_deterministic_toc`
- [x] Semantic section boundaries — MiniLM coherence in `build_ultimate_sections()`

### Phase 7 — Folder shims ✅
- [x] `backend/engine/` — re-exports pipeline/registry
- [x] `backend/web_platform/` — re-exports services (not `platform/` — stdlib conflict)
- [x] `backend/app/` — re-exports FastAPI `app`

---

## 3. Key Files

| Area | Path |
|------|------|
| Ingestion profiles | `src/modules/ingestion/profile.py` |
| Stage registry | `src/modules/pipeline/stage_registry.py` |
| FLAN 15f | `structure/final_structuring/models/flan_title_cleaner.py` |
| RAG rerank | `src/modules/rag/reranker.py` |
| RAG context | `src/modules/rag/context_builder.py` |
| Lazy RAG | `services/rag_index_helper.py` |
| PDF outline | `src/modules/ingestion/pdf_outline.py` |
| Benchmark | `scripts/bench_15f_cleanup.py` |

---

## 4. Default `fast_local` env

```env
INGESTION_PROFILE=fast_local
UPLOAD_SKIP_RAG=true
HEADING_CLEANUP_BACKEND=flan
RAG_RERANK_ENABLED=true
```

---

## 5. Validation

```bash
cd backend
python -m pytest tests/unit/ -q
python scripts/bench_15f_cleanup.py --modes rules,flan
```

Manual: upload PDF → logs under `logs/run_*/s*.json` → first ask builds RAG index → Q&A uses reranked context with `[1]` citations.

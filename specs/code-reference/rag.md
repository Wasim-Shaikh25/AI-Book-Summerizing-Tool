# Code Reference — RAG

> **Package:** `backend/src/modules/rag/`  
> **Module spec:** [../modules/rag-retrieval.md](../modules/rag-retrieval.md)

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `service.py` | `RagService` index lifecycle + retrieve API | Single entry for web/CLI |
| `chunk_builder.py` | Section → overlapping chunks (3 strategies) | Long sections need multiple retrieval units; semantic/paragraph boundaries improve precision |
| `corpus_builder.py` | Multi-book corpus FAISS index lifecycle | Cross-book search with lazy build + invalidation (Phase 5B) |
| `indexer.py` | FAISS build/load/save | Fast vector search local |
| `retriever.py` | Hybrid lexical + vector fusion | Legal terms need keyword + semantic |
| `reranker.py` | Cross-encoder rerank top-k | Precision after hybrid recall |
| `context_builder.py` | Dedupe + format Q&A context string | LLM context window limits |

---

## `service.py` — `RagService`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `ensure_index(book_id, sections, lines, log_dir)` | Build or load FAISS index | Lazy index on first ask (`UPLOAD_SKIP_RAG`) | `ChatService`, `rag_index_helper` |
| `retrieve(book_id, question, top_k)` | Hybrid retrieve + rerank | Q&A evidence selection | `BookQaEngine` |

---

## `chunk_builder.py` — chunk strategies (Phase 5A)

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `sections_to_rag_chunks(sections, *, book_id, ...)` | Section list → chunk records (strategy dispatch) | One chunk per section default; paragraph/semantic opts for higher precision | `ensure_index`, `corpus_builder` |
| `_semantic_boundary_split(text, heading, *, target_chars, overlap_sents) → list[dict]` | Split on paragraph/sentence boundaries with overlap | Prevents embedding averaging across unrelated sub-topics | `sections_to_rag_chunks` |
| `_split_words(text, *, size, overlap) → list[str]` | Legacy word-window split (used when `RAG_CHUNK_SIZE_WORDS > 0`) | Backward-compat with word-count chunking | `sections_to_rag_chunks` |

**Chunk metadata fields added (Phase 5A):** `paragraph_idx`, `sentence_start`, `sentence_end`, `chunk_strategy` (`"section"` / `"paragraph"` / `"semantic"` / `"word_window"`).

**Env vars:** `RAG_CHUNK_STRATEGY` (default `"section"`), `RAG_SEMANTIC_CHUNK_TARGET_CHARS` (default `500`), `RAG_SEMANTIC_OVERLAP_SENTS` (default `1`).

---

## `corpus_builder.py` — multi-book corpus index (Phase 5B)

**Purpose:** Aggregate per-book chunk files into a single FAISS corpus index for cross-book search.
**Why:** `RagService.retrieve` is scoped to one book; cross-book Q&A requires a merged index.
**Activated by:** `RAG_CORPUS_INDEX_ENABLED=1` (default `0`).

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_corpus_index(book_ids, user_id, *, data_dir, rag_repo, embedding_model) → Any` | Aggregate chunks from all books → FAISS index at `corpus_{user_id}/` | Lazy index build on first cross-book query | `RagService.retrieve_cross_book` |
| `load_corpus_index(user_id, *, data_dir) → Any \| None` | Load corpus index or return `None` | Check if built before building | `RagService.retrieve_cross_book` |
| `invalidate_corpus_index(user_id, *, data_dir)` | Delete corpus directory | Called when a book is added/removed | API handlers (manual call) |

**RagService additions:** `retrieve_cross_book(query, user_id, *, book_ids, top_k) → list[dict]` — returns `[]` when disabled.

---

## `indexer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_faiss_index(chunks, embedder)` | Embed + build index | First-time index | `ensure_index` |
| `load_faiss_index(book_id, dir)` | Load from `output/rag_index/` | Reuse across sessions | `ensure_index` |
| `FaissVectorIndex` | Wrapper for add/search/save | Isolate faiss-cpu API | Service |

---

## `retriever.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `hybrid_retrieve(question, chunks, index, weights)` | Vector + lexical fusion | Statute names match lexically; concepts match semantically | `RagService.retrieve` |
| `chunks_to_sections(chunks)` | Map chunks back to section ids | Q&A cites whole sections | `BookQaEngine` |

---

## `reranker.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `get_rag_reranker()` | Lazy cross-encoder singleton | Model load is expensive | `retrieve` |
| `rerank_chunks(question, chunks, top_k)` | Re-score top candidates | Hybrid recall is noisy on long books | `RagService.retrieve` |

---

## `context_builder.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `dedupe_sections(sections)` | Remove duplicate section hits | Multiple chunks same section | `build_qa_context` |
| `build_qa_context(sections, max_chars)` | Format citations for LLM | Bounded context + provenance | `BookQaEngine` |

# Code Reference — Knowledge Graph

> **Package:** `backend/src/modules/knowledge/`
> **Phase:** 7 — Concept Linking & Knowledge Graph
> **Pre-requisites:** Phase 5B (corpus_builder) and Phase 6 (qa_reasoning) complete.

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `__init__.py` | Package marker + docstring | Declares the package; documents the 3 modules |
| `concept_extractor.py` | NP extraction + TF scoring + optional MiniLM deduplication | Extract concepts from chunk text without LLM calls |
| `concept_graph.py` | Build/query SQLite concept graph (nodes, edges, BFS traversal) | Persist concept relationships for multi-hop retrieval |
| `graph_retriever.py` | Combined RAG + concept graph traversal retrieval | Surface semantically adjacent nodes not in RAG top-k |

---

## `concept_extractor.py`

**Purpose:** Extract top-k concepts from chunk text. No LLM. No domain vocabulary.
**Why:** Concept labels are needed to build the knowledge graph without API cost per chunk.
**Falls back to:** frequency-only scoring when `sentence-transformers` unavailable.

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `ExtractedConcept` | Dataclass: `canonical_name`, `aliases`, `salience_score`, `chunk_id`, `book_id` | Typed concept record for graph ingestion | `build_concept_graph`, `graph_retriever` |
| `extract_concepts_from_chunk(chunk_text, chunk_id, book_id, *, top_k) → list[ExtractedConcept]` | NP regex → normalise → TF score → MiniLM dedup → return top_k | Central extraction entry point | `concept_graph.build_concept_graph`, `graph_retriever.retrieve_with_graph` |
| `_normalise(phrase) → str` | Lowercase + strip leading/trailing stopwords | Canonical form for deduplication | `extract_concepts_from_chunk` |
| `_NP_RE` | Regex: `(DET? ADJ* NOUN+)` | Domain-agnostic noun-phrase candidate extractor | `extract_concepts_from_chunk` |
| `_STOPWORDS` | Frozenset of 60 common English stopwords | Edge-strip during normalisation | `_normalise` |
| `_get_model(model_name) → SentenceTransformer \| None` | Lazy-load MiniLM; returns `None` when unavailable | Graceful degradation | `extract_concepts_from_chunk` |

**Env vars:** None. `sentence-transformers` is optional.

---

## `concept_graph.py`

**Purpose:** Write and query SQLite concept nodes, chunk associations, and similarity links.
**Why:** SQLite is the project's only storage dependency; BFS traversal over concept_links enables multi-hop retrieval.
**Idempotent:** All writes use `INSERT OR IGNORE`.

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_concept_graph(concepts, *, db_path, similarity_threshold) → None` | Write concept_nodes + concept_chunks + concept_links to SQLite | Persist graph from extracted concepts | `graph_retriever.retrieve_with_graph`, scripts |
| `get_concept_by_name(name, *, db_path) → dict \| None` | Exact match lookup on `canonical_name` | Look up a concept node by name | `graph_retriever.retrieve_with_graph` |
| `get_related_concepts(concept_id, *, db_path, max_hops) → list[dict]` | BFS walk over concept_links up to max_hops | Multi-hop concept traversal | `graph_retriever.retrieve_with_graph` |
| `_concept_id(canonical_name) → str` | SHA-256[:16] hash of canonical_name | Stable, collision-resistant primary key | `build_concept_graph` |
| `_ensure_tables(cur)` | `CREATE TABLE IF NOT EXISTS` for all 3 tables | Migration-safe table creation for standalone use | `build_concept_graph` |

**DB tables added to `knowledge_base.db`:**
- `concept_nodes (concept_id PK, canonical_name, subject_area, embedding BLOB)`
- `concept_chunks (concept_id, chunk_id, book_id, salience_score; PK composite)`
- `concept_links (from_concept_id, to_concept_id, relation_type, evidence_chunk_ids JSON, link_strength; PK composite)`

**Env vars:** None. `sentence-transformers` is optional (skips similarity links if unavailable).

---

## `graph_retriever.py`

**Purpose:** Combined RAG + concept graph traversal retrieval.
**Why:** Pure vector retrieval misses semantically adjacent concepts not in top-k embedding results; graph traversal surfaces evidence chunks for related concept nodes.
**Falls back to:** pure RAG results when concept tables are empty or `retrieve_with_graph` called with no graph data.

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `retrieve_with_graph(query, rag_service, *, db_path, book_id, max_hops, top_k_chunks) → list[dict]` | RAG → concept extraction → graph walk → merge + deduplicate → re-rank | Multi-hop grounded retrieval | `qa_reasoning.py` (when `KNOWLEDGE_GRAPH_ENABLED=1`), scripts |

**Algorithm:**
1. Standard RAG → top `top_k_chunks // 2` chunks.
2. Extract concepts from those chunks via `concept_extractor`.
3. Look up concept nodes in SQLite.
4. BFS walk concept_links (`max_hops`).
5. Retrieve evidence chunk IDs from `concept_chunks`.
6. Merge; deduplicate by `chunk_id`; RAG results rank first.
7. Return top `top_k_chunks`.

**Env vars:** `KNOWLEDGE_GRAPH_ENABLED` (default `0`); `graph_retriever` is not wired into the pipeline by default.

"""Knowledge graph package — concept extraction, graph building, and graph-augmented retrieval.

Phase 7 of the Document Research Engine roadmap.

Modules:
  concept_extractor  — extract concepts from chunk text (no LLM, no domain vocabulary)
  concept_graph      — build/query SQLite concept graph (nodes, chunks, links)
  graph_retriever    — combined RAG + graph traversal retrieval
"""

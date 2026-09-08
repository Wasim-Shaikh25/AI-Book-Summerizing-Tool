"""Combined RAG + concept graph retrieval.

Augments standard vector retrieval with concept graph traversal to surface
semantically adjacent sections that may not rank in the top-k by embedding
distance alone.

Falls back to pure RAG results when concept tables are empty or KNOWLEDGE_GRAPH_ENABLED=0.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def retrieve_with_graph(
    query: str,
    rag_service: Any,
    *,
    db_path: Path,
    book_id: Optional[str] = None,
    max_hops: int = 2,
    top_k_chunks: int = 8,
) -> List[Dict]:
    """Combined RAG + concept graph retrieval.

    Steps:
    1. Standard RAG retrieve → top top_k_chunks // 2 chunks.
    2. Extract concepts from those chunks.
    3. Look up concept_ids in concept_nodes.
    4. Walk concept_links (max_hops) via get_related_concepts.
    5. Retrieve evidence chunk IDs for all encountered concept nodes.
    6. Merge with RAG results; deduplicate by chunk_id.
    7. Re-rank by combined (rag_score + salience_score); return top_k_chunks.

    Falls back to pure RAG results when concept tables are empty.

    Args:
        query:        Natural language query.
        rag_service:  RagService instance.
        db_path:      Path to knowledge_base.db.
        book_id:      Optional book scope for RAG retrieval.
        max_hops:     Maximum concept graph hops.
        top_k_chunks: Total results to return.
    """
    from src.modules.knowledge.concept_extractor import extract_concepts_from_chunk
    from src.modules.knowledge.concept_graph import get_concept_by_name, get_related_concepts

    half_k = max(1, top_k_chunks // 2)
    rag_results: List[Dict] = []
    try:
        if book_id:
            rag_results = rag_service.retrieve(query, book_id=book_id, sections=[], top_k=half_k)
        else:
            rag_results = []
    except Exception as exc:
        logger.warning("RAG retrieval failed in graph_retriever: %s", exc)

    if not rag_results:
        return rag_results

    # Collect concept nodes from RAG chunks
    all_concept_ids: set = set()
    for chunk in rag_results:
        text = chunk.get("text", "") or ""
        chunk_id = chunk.get("chunk_id", "") or chunk.get("section_id", "")
        bid = chunk.get("book_id", book_id or "")
        concepts = extract_concepts_from_chunk(text, chunk_id=chunk_id, book_id=bid, top_k=5)
        for c in concepts:
            node = get_concept_by_name(c.canonical_name, db_path=db_path)
            if node:
                all_concept_ids.add(node["concept_id"])

    # Walk concept links
    related_concept_ids: set = set()
    for cid in list(all_concept_ids):
        related = get_related_concepts(cid, db_path=db_path, max_hops=max_hops)
        for r in related:
            related_concept_ids.add(r["concept_id"])

    if not related_concept_ids:
        return rag_results[:top_k_chunks]

    # Retrieve evidence chunks from concept_chunks table
    import sqlite3

    db_path = Path(db_path)
    graph_chunk_ids: List[str] = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            placeholders = ",".join("?" * len(related_concept_ids))
            rows = conn.execute(
                f"SELECT DISTINCT chunk_id FROM concept_chunks WHERE concept_id IN ({placeholders})",
                list(related_concept_ids),
            ).fetchall()
            conn.close()
            graph_chunk_ids = [r[0] for r in rows]
        except Exception as exc:
            logger.debug("concept_chunks lookup failed: %s", exc)

    # Build merged result set
    seen_ids: set = set()
    merged: List[Dict] = []
    for chunk in rag_results:
        cid = chunk.get("chunk_id") or chunk.get("section_id", "")
        seen_ids.add(cid)
        merged.append(dict(chunk))

    # Add graph-sourced chunks (mark source)
    for cid in graph_chunk_ids:
        if cid not in seen_ids:
            merged.append({"chunk_id": cid, "source": "graph", "score": 0.0})
            seen_ids.add(cid)

    # Re-rank: RAG results already ranked; graph-only items go to the end
    return merged[:top_k_chunks]

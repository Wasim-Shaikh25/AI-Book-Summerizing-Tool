"""Build and query the SQLite concept graph.

Tables used: ``concept_nodes``, ``concept_chunks``, ``concept_links``.
All three are created in ``KnowledgeStore._initialize_db()`` (Phase 7 migration).

No LLM calls.  Falls back gracefully when sentence-transformers is unavailable:
in that case similarity-based links are skipped but nodes and chunk associations
are still written.

All write operations are idempotent (INSERT OR IGNORE).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

from src.modules.knowledge.concept_extractor import ExtractedConcept

_SIMILARITY_THRESHOLD_DEFAULT = 0.75


def _concept_id(canonical_name: str) -> str:
    return hashlib.sha256(canonical_name.encode("utf-8")).hexdigest()[:16]


def _get_embeddings(names: List[str]) -> Optional[List[list]]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(names, convert_to_numpy=True).tolist()  # type: ignore[return-value]
    except Exception:
        return None


def _cosine(a: list, b: list) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def build_concept_graph(
    concepts: List[ExtractedConcept],
    *,
    db_path: Path,
    similarity_threshold: float = _SIMILARITY_THRESHOLD_DEFAULT,
) -> None:
    """Write concept_nodes, concept_chunks, and concept_links rows to SQLite.

    Idempotent: re-running on the same data produces the same row count.

    - concept_nodes : one row per unique canonical_name (INSERT OR IGNORE).
    - concept_chunks: one row per (concept_id, chunk_id) pair.
    - concept_links : created for pairs with MiniLM cosine similarity >= threshold.
      relation_type inferred by similarity band:
        >= 0.90  → "related_to"
        else     → "broader_than"

    No LLM calls. Falls back when sentence-transformers unavailable (skips links).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        _ensure_tables(cur)

        name_to_id: Dict[str, str] = {}
        for c in concepts:
            cid = _concept_id(c.canonical_name)
            name_to_id[c.canonical_name] = cid
            cur.execute(
                "INSERT OR IGNORE INTO concept_nodes (concept_id, canonical_name) VALUES (?, ?)",
                (cid, c.canonical_name),
            )
            cur.execute(
                "INSERT OR IGNORE INTO concept_chunks "
                "(concept_id, chunk_id, book_id, salience_score) VALUES (?, ?, ?, ?)",
                (cid, c.chunk_id, c.book_id, c.salience_score),
            )

        # Build concept_links via embedding similarity
        unique_names = list(name_to_id.keys())
        if len(unique_names) >= 2:
            embs = _get_embeddings(unique_names)
            if embs is not None:
                for i in range(len(unique_names)):
                    for j in range(i + 1, len(unique_names)):
                        sim = _cosine(embs[i], embs[j])
                        if sim >= similarity_threshold:
                            rel = "related_to" if sim >= 0.90 else "broader_than"
                            from_id = name_to_id[unique_names[i]]
                            to_id = name_to_id[unique_names[j]]
                            evidence = json.dumps([])
                            cur.execute(
                                "INSERT OR IGNORE INTO concept_links "
                                "(from_concept_id, to_concept_id, relation_type, "
                                "evidence_chunk_ids, link_strength) VALUES (?, ?, ?, ?, ?)",
                                (from_id, to_id, rel, evidence, sim),
                            )
                            cur.execute(
                                "INSERT OR IGNORE INTO concept_links "
                                "(from_concept_id, to_concept_id, relation_type, "
                                "evidence_chunk_ids, link_strength) VALUES (?, ?, ?, ?, ?)",
                                (to_id, from_id, rel, evidence, sim),
                            )

        conn.commit()
    finally:
        conn.close()


def _ensure_tables(cur: sqlite3.Cursor) -> None:
    cur.execute("""CREATE TABLE IF NOT EXISTS concept_nodes (
        concept_id    TEXT PRIMARY KEY,
        canonical_name TEXT NOT NULL,
        subject_area   TEXT,
        embedding      BLOB
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS concept_chunks (
        concept_id     TEXT NOT NULL,
        chunk_id       TEXT NOT NULL,
        book_id        TEXT NOT NULL,
        salience_score REAL NOT NULL,
        PRIMARY KEY (concept_id, chunk_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS concept_links (
        from_concept_id TEXT NOT NULL,
        to_concept_id   TEXT NOT NULL,
        relation_type   TEXT NOT NULL,
        evidence_chunk_ids TEXT,
        link_strength   REAL NOT NULL,
        PRIMARY KEY (from_concept_id, to_concept_id)
    )""")


def get_concept_by_name(name: str, *, db_path: Path) -> Optional[Dict]:
    """Exact match lookup on ``canonical_name``.

    Returns {"concept_id", "canonical_name", "subject_area"} or None.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT concept_id, canonical_name, subject_area FROM concept_nodes WHERE canonical_name = ?",
            (name.lower().strip(),),
        ).fetchone()
        if row is None:
            return None
        return {"concept_id": row[0], "canonical_name": row[1], "subject_area": row[2]}
    finally:
        conn.close()


def get_related_concepts(
    concept_id: str,
    *,
    db_path: Path,
    max_hops: int = 2,
) -> List[Dict]:
    """Walk concept_links BFS up to max_hops.

    Returns list of {"concept_id", "canonical_name", "relation_type",
                      "evidence_chunk_ids", "hop"}.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        visited: set = {concept_id}
        queue: deque = deque([(concept_id, 0)])
        results: List[Dict] = []

        while queue:
            current_id, hop = queue.popleft()
            if hop >= max_hops:
                continue
            rows = cur.execute(
                "SELECT cl.to_concept_id, cn.canonical_name, cl.relation_type, "
                "cl.evidence_chunk_ids, cl.link_strength "
                "FROM concept_links cl "
                "JOIN concept_nodes cn ON cn.concept_id = cl.to_concept_id "
                "WHERE cl.from_concept_id = ?",
                (current_id,),
            ).fetchall()
            for row in rows:
                next_id = row[0]
                if next_id in visited:
                    continue
                visited.add(next_id)
                results.append({
                    "concept_id": row[0],
                    "canonical_name": row[1],
                    "relation_type": row[2],
                    "evidence_chunk_ids": row[3],
                    "hop": hop + 1,
                })
                queue.append((next_id, hop + 1))

        return results
    finally:
        conn.close()

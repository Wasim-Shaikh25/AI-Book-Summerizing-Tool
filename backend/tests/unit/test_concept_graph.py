"""Unit tests for concept_graph — SQLite node/edge creation and traversal."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.knowledge.concept_extractor import ExtractedConcept
from src.modules.knowledge.concept_graph import (  # noqa: E402
    build_concept_graph,
    get_concept_by_name,
    get_related_concepts,
)


def _make_concept(name: str, chunk_id: str = "C1") -> ExtractedConcept:
    return ExtractedConcept(
        canonical_name=name,
        aliases=[name],
        salience_score=0.8,
        chunk_id=chunk_id,
        book_id="B1",
    )


def test_build_creates_concept_nodes_table(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    build_concept_graph([_make_concept("tort law")], db_path=db)
    import sqlite3
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT * FROM concept_nodes").fetchall()
    conn.close()
    assert len(rows) >= 1


def test_build_creates_concept_chunks_table(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    build_concept_graph([_make_concept("negligence")], db_path=db)
    import sqlite3
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT * FROM concept_chunks").fetchall()
    conn.close()
    assert len(rows) >= 1


def test_build_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    concepts = [_make_concept("contract")]
    build_concept_graph(concepts, db_path=db)
    build_concept_graph(concepts, db_path=db)  # second run — must not duplicate
    import sqlite3
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM concept_nodes").fetchone()[0]
    conn.close()
    assert count == 1


def test_get_concept_by_name_exact_match(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    build_concept_graph([_make_concept("vicarious liability")], db_path=db)
    result = get_concept_by_name("vicarious liability", db_path=db)
    assert result is not None
    assert result["canonical_name"] == "vicarious liability"


def test_get_concept_by_name_returns_none_when_missing(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    build_concept_graph([_make_concept("tort")], db_path=db)
    result = get_concept_by_name("photosynthesis", db_path=db)
    assert result is None


def test_get_related_concepts_respects_max_hops(tmp_path: Path) -> None:
    """With max_hops=1, only direct neighbours returned."""
    db = tmp_path / "kb.db"
    concepts = [
        _make_concept("concept_a", "C1"),
        _make_concept("concept_b", "C2"),
        _make_concept("concept_c", "C3"),
    ]
    build_concept_graph(concepts, db_path=db, similarity_threshold=0.0)
    node_a = get_concept_by_name("concept_a", db_path=db)
    if node_a is None:
        return  # skip if no nodes built (no sentence-transformers in CI)
    related = get_related_concepts(node_a["concept_id"], db_path=db, max_hops=1)
    hops = [r["hop"] for r in related]
    assert all(h <= 1 for h in hops)


def test_get_related_concepts_returns_list(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    build_concept_graph([_make_concept("law")], db_path=db)
    node = get_concept_by_name("law", db_path=db)
    if node is None:
        return
    result = get_related_concepts(node["concept_id"], db_path=db)
    assert isinstance(result, list)

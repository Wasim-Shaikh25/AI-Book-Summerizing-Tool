"""Hybrid lexical + vector retrieval."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from src.modules.generation.rewrite_validation import normalize_heading
from src.modules.rag.indexer import FaissVectorIndex

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(normalize_heading(text or "").lower()) if len(t) > 2}


def _lexical_scores(query: str, chunks: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    q = _tokens(query)
    if not q:
        return {}
    raw: Dict[str, float] = {}
    for ch in chunks:
        cid = str(ch.get("chunk_id") or "")
        heading = str(ch.get("heading") or "")
        body = str(ch.get("text") or "")[:4000]
        h_tok = _tokens(heading)
        b_tok = _tokens(body)
        score = len(q & h_tok) * 4.0 + len(q & b_tok) * 1.0
        if any(w in heading.lower() for w in query.lower().split() if len(w) > 3):
            score += 2.0
        if score > 0:
            raw[cid] = score
    if not raw:
        return {}
    max_s = max(raw.values()) or 1.0
    return {k: v / max_s for k, v in raw.items()}


def hybrid_retrieve(
    query: str,
    *,
    vector_index: FaissVectorIndex | None,
    top_k: int = 6,
    vector_weight: float = 0.65,
    lexical_weight: float = 0.35,
    min_score: float = 0.15,
) -> List[Dict[str, Any]]:
    """Fuse vector and lexical scores; return chunk dicts with `_score`."""
    chunks = vector_index.chunks if vector_index else []
    if not chunks:
        return []

    vec_map: Dict[str, float] = {}
    if vector_index is not None:
        for score, ch in vector_index.search(query, top_k=max(top_k * 3, top_k)):
            cid = str(ch.get("chunk_id") or "")
            if cid:
                vec_map[cid] = max(vec_map.get(cid, 0.0), float(score))

    lex_map = _lexical_scores(query, chunks)
    chunk_by_id = {str(c.get("chunk_id") or ""): c for c in chunks}

    ids = set(vec_map) | set(lex_map)
    fused: List[tuple[float, Dict[str, Any]]] = []
    for cid in ids:
        ch = chunk_by_id.get(cid)
        if not ch:
            continue
        vs = vec_map.get(cid, 0.0)
        ls = lex_map.get(cid, 0.0)
        final = vector_weight * vs + lexical_weight * ls
        if final < min_score and not (vs > 0.45 or ls > 0.5):
            continue
        row = dict(ch)
        row["_score"] = round(final, 4)
        row["_vector_score"] = round(vs, 4)
        row["_lexical_score"] = round(ls, 4)
        fused.append((final, row))

    fused.sort(key=lambda x: (-x[0], str(x[1].get("heading") or "")))
    if not fused and vector_index is not None:
        for score, ch in vector_index.search(query, top_k=top_k):
            row = dict(ch)
            row["_score"] = round(float(score), 4)
            fused.append((float(score), row))

    seen_sections: set[str] = set()
    out: List[Dict[str, Any]] = []
    for _, row in fused:
        sid = str(row.get("section_id") or row.get("heading") or "")
        if sid in seen_sections and len(out) >= top_k:
            continue
        seen_sections.add(sid)
        out.append(row)
        if len(out) >= top_k:
            break
    return out


def chunks_to_sections(chunks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map RAG chunks back to section-shaped dicts for Q&A context."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for ch in chunks:
        sid = str(ch.get("section_id") or ch.get("heading") or "")
        if sid in seen:
            continue
        seen.add(sid)
        out.append(
            {
                "section_id": ch.get("section_id"),
                "heading": ch.get("heading"),
                "chapter_heading": ch.get("chapter_heading"),
                "page_number": ch.get("page_number"),
                "text": ch.get("text"),
                "_rag_score": ch.get("_score"),
            }
        )
    return out

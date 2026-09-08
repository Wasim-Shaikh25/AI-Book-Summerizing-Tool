"""Extract concepts from chunk text using regex NP patterns and TF scoring.

No LLM calls. No domain vocabulary.  Falls back to frequency-only scoring when
``sentence-transformers`` is unavailable.

Algorithm:
1. Extract noun-phrase candidates via regex NP pattern (DET? ADJ* NOUN+).
2. Normalise candidates to lowercase; strip stopwords from edges.
3. Score by term frequency within the chunk (TF proxy).
4. Deduplicate using MiniLM cosine similarity (threshold 0.85) — treat
   near-duplicate phrases as aliases of the same concept.
5. Return top_k by salience_score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_NP_RE = re.compile(
    r"\b(?:(?:the|a|an|this|that|these|those|each|every|any|some|no)\s+)?"
    r"(?:(?:[A-Z][a-z]+|[a-z]+(?:-[a-z]+)*)\s+){0,3}"
    r"(?:[A-Z][a-z]+|[a-z]+(?:-[a-z]+)*)\b"
)

_STOPWORDS = frozenset([
    "the", "a", "an", "this", "that", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall", "can",
    "its", "their", "our", "your", "his", "her", "it", "they", "we",
    "he", "she", "you", "i", "and", "or", "but", "not", "with", "for",
    "of", "in", "on", "at", "to", "from", "by", "as", "if", "when",
    "which", "who", "whom", "whose", "where", "that", "how", "what",
])

# Lazy-loaded; None when sentence-transformers is unavailable
SentenceTransformer: Optional[type] = None
try:
    from sentence_transformers import SentenceTransformer  # type: ignore[assignment,no-redef]
except Exception:
    SentenceTransformer = None  # type: ignore[assignment]

_MODEL_CACHE: Dict[str, object] = {}
_DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _get_model(model_name: str = _DEFAULT_MODEL) -> Optional[object]:
    if SentenceTransformer is None:
        return None
    if model_name not in _MODEL_CACHE:
        try:
            _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
        except Exception:
            return None
    return _MODEL_CACHE[model_name]


def _normalise(phrase: str) -> str:
    words = phrase.lower().split()
    while words and words[0] in _STOPWORDS:
        words.pop(0)
    while words and words[-1] in _STOPWORDS:
        words.pop()
    return " ".join(words)


def _cosine(a: "list[float]", b: "list[float]") -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class ExtractedConcept:
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    salience_score: float = 0.0
    chunk_id: str = ""
    book_id: str = ""


def extract_concepts_from_chunk(
    chunk_text: str,
    chunk_id: str,
    book_id: str,
    *,
    top_k: int = 5,
) -> List[ExtractedConcept]:
    """Extract top_k concepts from chunk_text.

    Args:
        chunk_text: Source text to analyse.
        chunk_id:   Chunk identifier for provenance.
        book_id:    Book identifier for provenance.
        top_k:      Maximum number of concepts to return.

    Returns:
        List of ExtractedConcept sorted by salience_score descending.
    """
    if not chunk_text or not chunk_text.strip():
        return []

    # 1. Extract noun-phrase candidates
    raw_candidates = _NP_RE.findall(chunk_text)

    # 2. Normalise and filter
    freq: Dict[str, int] = {}
    aliases: Dict[str, List[str]] = {}
    for raw in raw_candidates:
        norm = _normalise(raw)
        if not norm or len(norm) < 2:
            continue
        freq[norm] = freq.get(norm, 0) + 1
        if norm not in aliases:
            aliases[norm] = []
        if raw.lower() != norm and raw.lower() not in aliases[norm]:
            aliases[norm].append(raw.lower())

    if not freq:
        return []

    # 3. Score by term frequency (normalised to 0–1)
    max_freq = max(freq.values())
    scored = {k: v / max_freq for k, v in freq.items()}

    # 4. Deduplicate with MiniLM (if available)
    model = _get_model()
    unique_names = list(scored.keys())
    if model is not None and len(unique_names) > 1:
        try:
            embeddings = model.encode(unique_names, convert_to_numpy=True)  # type: ignore[attr-defined]
            kept: List[str] = []
            emb_map: Dict[str, list] = {n: embeddings[i].tolist() for i, n in enumerate(unique_names)}
            for name in unique_names:
                is_dup = any(
                    _cosine(emb_map[name], emb_map[k]) >= 0.85
                    for k in kept
                )
                if not is_dup:
                    kept.append(name)
                else:
                    # Merge alias into kept concept with highest freq
                    best = max(kept, key=lambda k: _cosine(emb_map[name], emb_map[k]))
                    aliases[best] = aliases.get(best, []) + [name] + aliases.get(name, [])
        except Exception:
            kept = unique_names
    else:
        kept = unique_names

    # 5. Return top_k by salience_score
    sorted_kept = sorted(kept, key=lambda n: scored.get(n, 0), reverse=True)[:top_k]
    result: List[ExtractedConcept] = []
    seen_names: set = set()
    for name in sorted_kept:
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append(ExtractedConcept(
            canonical_name=name,
            aliases=aliases.get(name, []),
            salience_score=min(1.0, max(0.0, scored.get(name, 0.0))),
            chunk_id=chunk_id,
            book_id=book_id,
        ))
    return result

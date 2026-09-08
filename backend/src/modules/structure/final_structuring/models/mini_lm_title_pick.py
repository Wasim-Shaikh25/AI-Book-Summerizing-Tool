"""MiniLM-based title pick for weak headings (Stage 15f/15i)."""

from __future__ import annotations

from typing import List, Optional, Sequence, TYPE_CHECKING

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

if TYPE_CHECKING:
    from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry


def _candidate_titles(
    *,
    subheadings: Optional[Sequence[str]] = None,
    registry: Optional["DroppedHeadingRegistry"] = None,
) -> List[str]:
    out: List[str] = []
    for sub in subheadings or []:
        text = (sub or "").strip()
        if not text or is_weak_section_heading(text):
            continue
        if registry is not None and not registry.is_allowed_title(text):
            continue
        out.append(text[:120])
    seen: set[str] = set()
    unique: List[str] = []
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _preview_candidates(
    preview: str,
    *,
    registry: Optional["DroppedHeadingRegistry"] = None,
) -> List[str]:
    """Derive title candidates from source body preview (not used verbatim as title)."""
    from src.modules.structure.final_structuring.heading_title_engine import title_from_fragment_preview

    text = (preview or "").strip()
    if not text:
        return []
    candidates: List[str] = []
    frag_title = title_from_fragment_preview({"fragment": {"preview": text}})
    if frag_title:
        candidates.append(frag_title)
    for line in text.splitlines()[:3]:
        line = line.strip()
        if len(line.split()) < 4:
            continue
        short = " ".join(line.split()[:10])
        if not is_weak_section_heading(short) and short not in candidates:
            if registry is None or registry.is_allowed_title(short):
                candidates.append(short[:120])
    seen: set[str] = set()
    unique: List[str] = []
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def mini_lm_pick_title(
    heading: str,
    *,
    preview: str = "",
    subheadings: Optional[Sequence[str]] = None,
    threshold: float = 0.82,
    registry: Optional["DroppedHeadingRegistry"] = None,
) -> Optional[str]:
    """Pick a strong title using MiniLM — subheadings + preview-derived candidates."""
    sub_candidates = _candidate_titles(subheadings=subheadings, registry=registry)
    preview_candidates = _preview_candidates(preview, registry=registry) if preview else []
    candidates: List[str] = []
    seen: set[str] = set()
    for item in sub_candidates + preview_candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(item)
    if not candidates:
        return None

    encoder = get_mini_lm_encoder()
    query = (preview[:400].strip() if preview else (heading or "").strip())
    if not query:
        return None

    query_emb = encoder.encode([query])
    corpus_emb = encoder.encode(candidates)
    if query_emb is None or corpus_emb is None:
        return None

    sims = corpus_emb @ query_emb[0]
    best_idx = int(sims.argmax())
    best_sim = float(sims[best_idx])
    if best_sim < threshold:
        return None

    picked = candidates[best_idx]
    if is_weak_section_heading(picked):
        return None
    if registry is not None and not registry.is_allowed_title(picked):
        return None
    return picked

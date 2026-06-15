"""Merge consecutive chapters when topics are related (MiniLM + heading overlap)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.modules.generation.rewrite_validation import is_weak_section_heading, normalize_heading
from src.modules.structure.final_structuring.chapter_merger import (
    _chapter_chars,
    _is_hard_break_heading,
    _merge_chapter_into,
    _norm,
    _section_count,
)
from src.shared import config

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "of",
        "in",
        "to",
        "a",
        "an",
        "for",
        "on",
        "act",
        "law",
        "section",
        "article",
        "chapter",
        "part",
        "india",
        "indian",
    }
)


def _section_labels(sec: Dict[str, Any]) -> List[str]:
    labels = [_norm(str(sec.get("heading") or ""))]
    for sub in sec.get("subheadings") or []:
        h = _norm(str(sub.get("heading") or ""))
        if h and not is_weak_section_heading(h):
            labels.append(h)
    return [x for x in labels if x]


def section_topic_text(sec: Dict[str, Any]) -> str:
    parts = _section_labels(sec)
    preview = _norm(str((sec.get("fragment") or {}).get("preview") or ""))[:200]
    if preview:
        parts.append(preview)
    return " — ".join(parts)[:400]


def chapter_topic_text(chapter: Dict[str, Any]) -> str:
    parts: List[str] = []
    title = _norm(str(chapter.get("heading") or ""))
    if title:
        parts.append(title)
    for sec in chapter.get("sections") or []:
        text = section_topic_text(sec)
        if text:
            parts.append(text)
    return " | ".join(parts)[:1200]


def _token_set(text: str) -> set[str]:
    tokens = {t.lower() for t in re.findall(r"[a-zA-Z]{3,}", text or "")}
    return {t for t in tokens if t not in _STOPWORDS}


def _heading_overlap_score(ch_a: Dict[str, Any], ch_b: Dict[str, Any]) -> float:
    """Lexical overlap between chapter section headings (cheap relatedness signal)."""
    heads_a = {_norm(str(s.get("heading") or "")) for s in ch_a.get("sections") or []}
    heads_b = {_norm(str(s.get("heading") or "")) for s in ch_b.get("sections") or []}
    heads_a = {normalize_heading(h) for h in heads_a if h and not is_weak_section_heading(h)}
    heads_b = {normalize_heading(h) for h in heads_b if h and not is_weak_section_heading(h)}
    if not heads_a or not heads_b:
        return 0.0
    inter = len(heads_a & heads_b)
    union = len(heads_a | heads_b)
    return inter / union if union else 0.0


def _embedding_similarity(text_a: str, text_b: str) -> Optional[float]:
    if not text_a.strip() or not text_b.strip():
        return None
    try:
        from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

        encoder = get_mini_lm_encoder()
        emb = encoder.encode([text_a, text_b])
        if emb is None or len(emb) < 2:
            return None
        import numpy as np

        a = emb[0]
        b = emb[1]
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 0:
            return None
        return float(np.dot(a, b) / denom)
    except Exception as exc:
        logger.debug("chapter cohesion embedding skipped: %s", exc)
        return None


def chapters_are_related(
    ch_a: Dict[str, Any],
    ch_b: Dict[str, Any],
    *,
    threshold: float = 0.52,
) -> bool:
    """True when the next chapter continues the same study theme as the previous."""
    title_a = _norm(str(ch_a.get("heading") or ""))
    title_b = _norm(str(ch_b.get("heading") or ""))
    if _is_hard_break_heading(title_a) or _is_hard_break_heading(title_b):
        return False

    overlap = _heading_overlap_score(ch_a, ch_b)
    if overlap >= 0.22:
        return True

    tokens_a = _token_set(chapter_topic_text(ch_a))
    tokens_b = _token_set(chapter_topic_text(ch_b))
    if tokens_a and tokens_b:
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        if jaccard >= 0.18:
            return True

    sim = _embedding_similarity(chapter_topic_text(ch_a), chapter_topic_text(ch_b))
    if sim is not None and sim >= threshold:
        return True
    return False


def sections_are_related(sec_a: Dict[str, Any], sec_b: Dict[str, Any], *, threshold: float = 0.48) -> bool:
    """True when consecutive sections belong under the same chapter umbrella."""
    ha = _norm(str(sec_a.get("heading") or ""))
    hb = _norm(str(sec_b.get("heading") or ""))
    if _is_hard_break_heading(hb):
        return False
    if normalize_heading(ha) == normalize_heading(hb):
        return True

    tokens_a = _token_set(section_topic_text(sec_a))
    tokens_b = _token_set(section_topic_text(sec_b))
    if tokens_a and tokens_b:
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        if jaccard >= 0.2:
            return True

    sim = _embedding_similarity(section_topic_text(sec_a), section_topic_text(sec_b))
    return sim is not None and sim >= threshold


def coalesce_regroup_assignments(
    assignments: List[Dict[str, Any]],
    sections: Sequence[Dict[str, Any]],
    *,
    cohesion_threshold: float = 0.48,
) -> int:
    """
    Before rebuilding chapters: if OpenAI marked a new chapter start but the next
    section is related to the previous one, keep it in the same chapter.
    """
    if len(assignments) < 2:
        return 0

    sec_by_id = {str(s.get("section_id")): s for s in sections}
    changed = 0
    prev_sec: Optional[Dict[str, Any]] = None
    current_chapter_title = ""

    for row in assignments:
        sid = str(row.get("section_id") or "")
        sec = sec_by_id.get(sid)
        if sec is None:
            continue

        if row.get("is_chapter_start"):
            if prev_sec is not None and sections_are_related(
                prev_sec, sec, threshold=cohesion_threshold
            ):
                row["is_chapter_start"] = False
                if current_chapter_title:
                    row["chapter_title"] = current_chapter_title
                changed += 1
            else:
                current_chapter_title = _norm(str(row.get("chapter_title") or ""))
        elif current_chapter_title:
            row["chapter_title"] = current_chapter_title

        prev_sec = sec

    return changed


def _pick_merged_chapter_title(ch_a: Dict[str, Any], ch_b: Dict[str, Any]) -> str:
    from src.modules.structure.final_structuring.chapter_placement import infer_chapter_title_from_sections

    combined = list(ch_a.get("sections") or []) + list(ch_b.get("sections") or [])
    inferred = infer_chapter_title_from_sections(combined)
    if inferred:
        return inferred[:120]
    a_title = _norm(str(ch_a.get("heading") or ""))
    b_title = _norm(str(ch_b.get("heading") or ""))
    if len(a_title) >= len(b_title):
        return a_title[:120]
    return b_title[:120]


def merge_related_adjacent_chapters(
    chapters: List[Dict[str, Any]],
    *,
    min_sections: int = 3,
    max_sections: int = 12,
    cohesion_threshold: float = 0.52,
    strong_cohesion_threshold: float = 0.68,
) -> Tuple[List[Dict[str, Any]], int]:
    """Merge consecutive chapters when topics are related and combined size fits."""
    if len(chapters) < 2:
        return chapters, 0

    merged_count = 0
    out: List[Dict[str, Any]] = []

    for ch in chapters:
        if not out:
            out.append(dict(ch))
            continue

        prev = out[-1]
        prev_secs = _section_count(prev)
        cur_secs = _section_count(ch)
        combined = prev_secs + cur_secs

        if combined > max_sections:
            out.append(dict(ch))
            continue

        both_substantial = prev_secs >= min_sections and cur_secs >= min_sections
        threshold = strong_cohesion_threshold if both_substantial else cohesion_threshold

        tiny_pair = prev_secs < min_sections or cur_secs < min_sections
        if tiny_pair or chapters_are_related(prev, ch, threshold=threshold):
            if not chapters_are_related(prev, ch, threshold=threshold) and not tiny_pair:
                out.append(dict(ch))
                continue
            if tiny_pair and not chapters_are_related(prev, ch, threshold=cohesion_threshold - 0.08):
                # Do not merge unrelated tiny chapters (e.g. Muslim law + Parsi law)
                if _heading_overlap_score(prev, ch) < 0.05:
                    out.append(dict(ch))
                    continue
            _merge_chapter_into(prev, ch)
            prev["heading"] = _pick_merged_chapter_title(prev, ch)
            merged_count += 1
            continue

        out.append(dict(ch))

    for i, ch in enumerate(out, start=1):
        ch["chapter_id"] = f"C{i}"
        sections = list(ch.get("sections") or [])
        if sections:
            ch["page_start"] = sections[0].get("page_number")
            ch["page_end"] = sections[-1].get("page_number")

    return out, merged_count


def consolidate_chapter_hierarchy(
    chapters: List[Dict[str, Any]],
    *,
    min_sections: Optional[int] = None,
    min_chars: Optional[int] = None,
    max_sections: Optional[int] = None,
    cohesion_threshold: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Run undersized merge + related-topic merge (15h / 15j)."""
    from src.modules.structure.final_structuring.chapter_merger import merge_undersized_chapters

    min_secs = int(
        min_sections
        if min_sections is not None
        else getattr(config, "CHAPTER_COHESION_MIN_SECTIONS", 3) or 3
    )
    min_ch = int(
        min_chars
        if min_chars is not None
        else getattr(config, "CHAPTER_COHESION_MIN_CHARS", 400) or 400
    )
    max_secs = int(
        max_sections
        if max_sections is not None
        else getattr(config, "CHAPTER_COHESION_MAX_SECTIONS", 12) or 12
    )
    threshold = float(
        cohesion_threshold
        if cohesion_threshold is not None
        else getattr(config, "CHAPTER_COHESION_THRESHOLD", 0.52) or 0.52
    )

    chapters, tiny_merged = merge_undersized_chapters(
        chapters,
        min_sections=min_secs,
        min_chars=min_ch,
    )
    chapters, related_merged = merge_related_adjacent_chapters(
        chapters,
        min_sections=min_secs,
        max_sections=max_secs,
        cohesion_threshold=threshold,
    )
    stats = {"tiny_merged": tiny_merged, "related_merged": related_merged}
    return chapters, stats

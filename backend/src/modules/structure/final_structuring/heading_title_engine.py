"""Title picking: rules + MiniLM similarity + optional cloud LLM fallback."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from src.shared.models import NormalizedLine

from src.modules.generation.rewrite_validation import is_weak_section_heading, normalize_heading
from src.modules.structure.dropped_heading_registry import (
    is_acceptable_study_title,
    is_sentence_like_title,
    is_syllabus_heading,
    title_from_subheadings,
)
from src.shared import config

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _filter_candidates(labels: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in labels:
        t = _norm(raw)
        if not t or not is_acceptable_study_title(t):
            continue
        key = normalize_heading(t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _minilm_embeddings(texts: Sequence[str]) -> Optional[np.ndarray]:
    from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

    clean = [t for t in texts if (t or "").strip()]
    if not clean:
        return None
    return get_mini_lm_encoder().encode(clean)


def _medoid_label(candidates: Sequence[str], context_texts: Sequence[str]) -> Optional[str]:
    """Pick the candidate closest to the semantic centroid (MiniLM)."""
    labels = _filter_candidates(candidates)
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]

    contexts = [t for t in context_texts if (t or "").strip()]
    emb = _minilm_embeddings(contexts or labels)
    if emb is not None and len(emb) > 0:
        centroid = np.mean(emb, axis=0)
        cand_emb = _minilm_embeddings(labels)
        if cand_emb is not None:
            sims = cand_emb @ centroid
            best = labels[int(np.argmax(sims))]
            if float(np.median(sims)) >= 0.45:
                return best
    return None


def _range_title(candidates: Sequence[str]) -> Optional[str]:
    labels = _filter_candidates(candidates)
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0][:120]
    if len(labels) == 2:
        return f"{labels[0]} — {labels[1]}"[:120]
    return f"{labels[0]} — {labels[-1]}"[:120]


def _cloud_title_fallback(
    *,
    candidates: Sequence[str],
    kind: str,
    preview: str = "",
    old_heading: str = "",
    chapter_heading: str = "",
    lines: Optional[Sequence[NormalizedLine]] = None,
    page_number: Optional[int] = None,
    require_strict: bool = False,
) -> Optional[str]:
    if not getattr(config, "HEADING_REFINEMENT_OPENAI_FALLBACK", False):
        return None
    labels = _filter_candidates(candidates)
    try:
        from src.modules.pipeline.llm_chat_client import LlmChatClient

        client = LlmChatClient.from_config(temperature=0.1)
        if preview.strip() and (old_heading or labels):
            user = (
                f"Write ONE short textbook {kind} title (max 10 words).\n"
                f"Chapter: {chapter_heading or '(unknown)'}\n"
                f"Weak PDF title: {old_heading or '(none)'}\n"
                f"Source excerpt:\n{preview[:900]}\n\n"
                "Use the statute/section number when present. Do not copy a sentence verbatim."
            )
        elif labels:
            topics = "; ".join(labels[:10])
            user = (
                f"Write ONE short textbook {kind} title (max 8 words) covering these topics. "
                f"Do not use 'A study of' or 'A history of'. Topics: {topics}"
            )
        else:
            return None
        out = (client.chat(system="You write concise academic headings only.", user=user, max_tokens=40) or "").strip()
        out = _norm(out).strip("\"'")
        if out and is_acceptable_study_title(out):
            from src.modules.structure.final_structuring.title_pdf_anchor import accept_edited_title

            return accept_edited_title(
                out[:120],
                old_heading,
                lines=lines,
                page_number=page_number,
                require_strict=require_strict,
            )
    except Exception as exc:
        logger.debug("Cloud title fallback failed: %s", exc)
    return None


def title_from_fragment_preview(section: Dict[str, Any], *, max_words: int = 8) -> str:
    """Derive a short topic label from section source preview when PDF heading is weak."""
    from src.modules.structure.dropped_heading_registry import case_hint_from_preview

    frag = section.get("fragment") or {}
    preview = _norm(str(frag.get("preview") or ""))
    if not preview:
        return ""

    hint = case_hint_from_preview(preview)
    if hint and is_acceptable_study_title(hint) and not is_syllabus_heading(hint):
        return hint[:120]

    line = preview.split("\n")[0].strip()
    line = re.sub(r"^[•\-\*·]\s+", "", line)
    line = re.split(r"[.;:]", line)[0].strip()
    if len(line.split()) < 3 or len(line) < 10:
        return ""
    if is_syllabus_heading(line):
        return ""

    title = " ".join(line.split()[:max_words])
    if is_acceptable_study_title(title):
        return title[:120]
    return ""


def section_context_text(sec: Dict[str, Any]) -> str:
    parts = [_norm(str(sec.get("heading") or ""))]
    frag = sec.get("fragment") or {}
    preview = _norm(str(frag.get("preview") or ""))[:200]
    if preview:
        parts.append(preview)
    for sub in sec.get("subheadings") or []:
        h = _norm(str(sub.get("heading") or ""))
        if h:
            parts.append(h)
    return " — ".join(p for p in parts if p)[:400]


def ensure_study_safe_heading(
    title: str,
    *,
    chapter_heading: str = "",
    page_number: Optional[int] = None,
    max_len: int = 120,
) -> str:
    """Last-resort repair so export/audit titles classify as looks_ok."""
    from src.modules.quality.heuristics import classify_heading
    from src.modules.structure.dropped_heading_registry import (
        is_acceptable_study_title,
        partition_heading_to_study_title,
    )

    def _ok(text: str) -> bool:
        t = (text or "").strip()
        return bool(t) and classify_heading(t) == "looks_ok" and is_acceptable_study_title(t)

    candidate = (title or "").strip()
    if _ok(candidate):
        return candidate[:max_len]

    if chapter_heading:
        parent = partition_heading_to_study_title(chapter_heading)
        if parent:
            with_page = f"{parent} (p. {page_number})" if page_number is not None else parent
            if _ok(with_page):
                return with_page[:max_len]
            if _ok(parent):
                return parent[:max_len]

    if page_number is not None:
        anchor = f"Content (p. {page_number})"
        if _ok(anchor):
            return anchor[:max_len]

    return (candidate or chapter_heading or "Section")[:max_len]


def resolve_section_display_heading(
    section: Dict[str, Any],
    *,
    chapter_heading: str = "",
    use_transformers: bool = True,
) -> str:
    """Export-safe section title — repair fragments before display."""
    from src.modules.structure.dropped_heading_registry import (
        is_acceptable_study_title,
        is_incomplete_pdf_heading,
        is_noisy_fragment_heading,
        is_structural_partition_heading,
    )
    from src.modules.quality.heuristics import classify_heading

    raw = _norm(str(section.get("heading") or ""))
    if raw:
        cls = classify_heading(raw)
        if (
            cls == "looks_ok"
            and is_acceptable_study_title(raw)
            and not is_incomplete_pdf_heading(raw)
            and not is_noisy_fragment_heading(raw)
            and not is_structural_partition_heading(raw)
        ):
            return raw[:120]
    picked = pick_section_title(section, chapter_heading=chapter_heading, use_transformers=use_transformers)
    return ensure_study_safe_heading(
        picked,
        chapter_heading=chapter_heading,
        page_number=section.get("page_number"),
    )


def resolve_chapter_display_heading(
    chapter: Dict[str, Any],
    *,
    use_transformers: bool = True,
) -> str:
    """Export-safe chapter title — strip CHAPTER I: prefixes; consistent study labels."""
    from src.modules.structure.dropped_heading_registry import (
        is_acceptable_study_title,
        is_structural_partition_heading,
        partition_heading_to_study_title,
    )

    sections = list(chapter.get("sections") or [])
    raw = _norm(str(chapter.get("heading") or ""))
    if is_structural_partition_heading(raw):
        normalized = partition_heading_to_study_title(raw)
        if normalized and is_acceptable_study_title(normalized):
            return normalized[:120]
        inferred = pick_chapter_title(sections, book_title="")
        return inferred[:120] if inferred else normalized[:120] or raw[:120]
    if raw and is_acceptable_study_title(raw):
        return raw[:120]
    inferred = pick_chapter_title(sections, book_title="")
    return (inferred or raw)[:120]


def pick_chapter_title(
    sections: Sequence[Dict[str, Any]],
    *,
    book_title: str = "",
    lines: Optional[Sequence[NormalizedLine]] = None,
    require_strict_heading_match: bool = False,
) -> str:
    """Chapter title from grouped sections — rules + MiniLM + optional cloud fallback."""
    secs = list(sections or [])
    if not secs:
        return "Chapter"
    pinned = _norm(book_title)
    if len(secs) == 1:
        h = _norm(str(secs[0].get("heading") or ""))
        return h[:120] if is_acceptable_study_title(h) else _range_title([h]) or "Chapter"

    from src.modules.structure.final_structuring.chapter_placement import is_structural_chapter_break

    for sec in secs:
        h = _norm(str(sec.get("heading") or ""))
        if is_structural_chapter_break(h):
            return h[:120]
        for sub in sec.get("subheadings") or []:
            sh = _norm(str(sub.get("heading") or ""))
            if is_structural_chapter_break(sh):
                return sh[:120]

    raw_candidates = [_norm(str(s.get("heading") or "")) for s in secs]
    candidates = _filter_candidates(raw_candidates)
    contexts = [section_context_text(s) for s in secs]

    syllabus_hits = sum(1 for c in raw_candidates if is_syllabus_heading(c))
    if pinned and syllabus_hits >= max(1, len(raw_candidates) // 2):
        return pinned[:120]

    for c in candidates:
        if len(c) >= 12 and c.isupper() and not is_syllabus_heading(c):
            return c[:120]

    medoid = _medoid_label(candidates, contexts)
    cohesion = 0.0
    if medoid:
        emb = _minilm_embeddings(contexts)
        if emb is not None and len(emb) > 1:
            centroid = np.mean(emb, axis=0)
            cohesion = float(np.mean(emb @ centroid))

    if len(secs) >= 3 and cohesion < 0.55:
        ranged = _range_title(candidates)
        if ranged:
            return ranged

    if medoid and is_acceptable_study_title(medoid):
        result = medoid[:120]
    else:
        ranged = _range_title(candidates)
        if ranged:
            result = ranged
        else:
            cloud = _cloud_title_fallback(
                candidates=candidates,
                kind="chapter",
                lines=lines,
                page_number=secs[0].get("page_number") if secs else None,
                require_strict=require_strict_heading_match,
            )
            if cloud:
                result = cloud
            else:
                pg = secs[0].get("page_number")
                result = f"Study topics (p. {pg})" if pg is not None else "Study topics"

    if len(secs) >= 2:
        from src.modules.quality.heuristics import chapter_mirrors_first_section

        first_h = _norm(str(secs[0].get("heading") or ""))
        if chapter_mirrors_first_section(result, first_h):
            alt = _range_title(_filter_candidates([_norm(str(s.get("heading") or "")) for s in secs]))
            if alt and not chapter_mirrors_first_section(alt, first_h):
                return alt[:120]
    return result[:120] if isinstance(result, str) else str(result)


def pick_section_title(
    section: Dict[str, Any],
    *,
    chapter_heading: str = "",
    use_transformers: bool = True,
    lines: Optional[Sequence[NormalizedLine]] = None,
    require_strict_heading_match: bool = False,
) -> str:
    """Section title — keep good PDF label; else MiniLM/cloud from subheadings + source preview."""
    from src.modules.structure.dropped_heading_registry import is_incomplete_pdf_heading
    from src.modules.structure.final_structuring.chapter_placement import universal_clean_heading
    from src.modules.structure.final_structuring.models.mini_lm_title_pick import mini_lm_pick_title

    raw = _norm(str(section.get("heading") or ""))
    subs = list(section.get("subheadings") or [])
    sub_labels = [_norm(str(s.get("heading") or "")) for s in subs]
    frag = section.get("fragment") or {}
    preview = _norm(str(frag.get("preview") or ""))

    from src.modules.structure.dropped_heading_registry import (
        is_statute_prose_heading,
        is_structural_partition_heading,
        topic_from_labeled_prose,
    )

    if is_structural_partition_heading(raw):
        from_preview = title_from_fragment_preview(section)
        if from_preview and is_acceptable_study_title(from_preview):
            return from_preview[:120]
        from_sub = title_from_subheadings(subs)
        if from_sub and is_acceptable_study_title(from_sub):
            return from_sub[:120]
        raw = ""

    # Subject-agnostic: pull a clean topic out of labeled body prose before any
    # other repair (e.g. "Section 309: Robbery. — Fund held…" -> "Robbery").
    if raw and is_statute_prose_heading(raw):
        topic = topic_from_labeled_prose(raw)
        if topic and is_acceptable_study_title(topic):
            return topic[:120]

    needs_repair = (
        not raw
        or is_incomplete_pdf_heading(raw)
        or is_statute_prose_heading(raw)
        or is_structural_partition_heading(raw)
        or is_sentence_like_title(raw)
        or len(raw.split()) > 12
        or len(raw) > 95
    )

    if needs_repair:
        from_preview = title_from_fragment_preview(section)
        if from_preview and is_acceptable_study_title(from_preview):
            return from_preview[:120]

    cleaned = universal_clean_heading(
        raw,
        subheadings=subs,
        page_number=section.get("page_number"),
        parent_heading=chapter_heading,
        preview=preview,
        use_transformers=False,
    )

    if is_acceptable_study_title(cleaned) and not is_syllabus_heading(cleaned) and not is_incomplete_pdf_heading(cleaned):
        first_sub = sub_labels[0] if sub_labels else ""
        if not first_sub or normalize_heading(cleaned) != normalize_heading(first_sub) or len(sub_labels) < 2:
            return cleaned[:120]

    from_sub = title_from_subheadings(subs)
    if from_sub and is_acceptable_study_title(from_sub) and not is_incomplete_pdf_heading(from_sub):
        if normalize_heading(from_sub) != normalize_heading(cleaned) or not is_acceptable_study_title(cleaned):
            return from_sub[:120]

    if use_transformers:
        threshold = float(getattr(config, "HEADING_REFINEMENT_MINILM_THRESHOLD", 0.78) or 0.78)
        picked = mini_lm_pick_title(
            cleaned or raw,
            preview=preview,
            subheadings=_filter_candidates(sub_labels),
            threshold=threshold,
        )
        if picked and is_acceptable_study_title(picked):
            return picked[:120]

    filtered = _filter_candidates(sub_labels)
    ranged = _range_title(filtered)
    if ranged and len(filtered) >= 2:
        return ranged

    if is_acceptable_study_title(cleaned) and not is_incomplete_pdf_heading(cleaned):
        return cleaned[:120]

    cloud = _cloud_title_fallback(
        candidates=filtered or [raw],
        kind="section",
        preview=preview,
        old_heading=raw,
        chapter_heading=chapter_heading,
        lines=lines,
        page_number=section.get("page_number"),
        require_strict=require_strict_heading_match,
    )
    if cloud:
        return cloud

    from_preview = title_from_fragment_preview(section)
    if from_preview:
        return from_preview[:120]

    pg = section.get("page_number")
    return f"Section topic (p. {pg})" if pg is not None else (cleaned or raw)[:120]


def pick_subheading_title(
    sub: Dict[str, Any],
    *,
    section_heading: str,
    chapter_heading: str = "",
    sibling_labels: Optional[Sequence[str]] = None,
    use_transformers: bool = True,
) -> str:
    """Subheading title — rules + MiniLM pick."""
    from src.modules.structure.dropped_heading_registry import case_hint_from_preview, is_structural_partition_heading
    from src.modules.structure.final_structuring.chapter_placement import universal_clean_heading
    from src.modules.structure.final_structuring.heading_cleanup import _strip_page_disambiguation_suffixes

    raw = _norm(str(sub.get("heading") or ""))
    if not raw:
        return raw
    if is_structural_partition_heading(raw):
        hint = case_hint_from_preview(_norm(str((sub.get("fragment") or {}).get("preview") or "")))
        if hint and is_acceptable_study_title(hint):
            return hint[:120]
        return ""

    cleaned = _strip_page_disambiguation_suffixes(raw)
    cleaned = universal_clean_heading(
        cleaned,
        subheadings=[],
        parent_heading=section_heading or chapter_heading,
        use_transformers=False,
    )

    if is_acceptable_study_title(cleaned):
        return cleaned[:120]

    if use_transformers:
        from src.modules.structure.final_structuring.models.mini_lm_title_pick import mini_lm_pick_title

        siblings = [s for s in (sibling_labels or []) if s and s != raw]
        threshold = float(getattr(config, "HEADING_REFINEMENT_MINILM_THRESHOLD", 0.8) or 0.8)
        picked = mini_lm_pick_title(cleaned, subheadings=_filter_candidates(siblings), threshold=threshold)
        if picked and is_acceptable_study_title(picked):
            return picked[:120]

    hint = case_hint_from_preview(_norm(str((sub.get("fragment") or {}).get("preview") or "")))
    if hint and is_acceptable_study_title(hint):
        return hint[:120]

    return cleaned[:120] if cleaned else raw[:120]

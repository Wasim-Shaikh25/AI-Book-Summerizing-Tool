"""Stage 15h — universal chapter splits, section reassignment, and title refinement."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.modules.generation.rewrite_validation import is_weak_section_heading, normalize_heading
from src.modules.structure.dropped_heading_registry import title_from_subheadings
from src.modules.structure.final_structuring.chapter_hierarchy_builder import _looks_like_chapter_heading
from src.shared import config
from src.shared.english_text import filter_english_heading

logger = logging.getLogger(__name__)

_MODULE_UNIT_RE = re.compile(r"^\s*(module|unit)\s+\d+", re.I)
_BULLET_PREFIX = re.compile(r"^[•\-\*·]\s+")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_structural_chapter_break(heading: str) -> bool:
    """True for MODULE/UNIT/PART/CHAPTER N and major ALL-CAPS partition lines."""
    from src.modules.structure.dropped_heading_registry import is_structural_partition_heading

    return is_structural_partition_heading(heading)


def section_starts_new_part(sec: Dict[str, Any]) -> bool:
    """True when a section (or its leading subheading) should begin a new chapter."""
    heading = _norm(str(sec.get("heading") or ""))
    if is_structural_chapter_break(heading):
        return True
    subs = sec.get("subheadings") or []
    if subs:
        first_sub = _norm(str(subs[0].get("heading") or ""))
        if is_structural_chapter_break(first_sub):
            return True
    return False


def _chapter_page_numbers(chapter: Dict[str, Any]) -> List[int]:
    pages: List[int] = []
    for sec in chapter.get("sections") or []:
        pg = sec.get("page_number")
        if pg is not None:
            pages.append(int(pg))
    return pages


def _section_page_fits_chapter(
    sec: Dict[str, Any],
    chapter: Dict[str, Any],
    *,
    margin: int,
) -> bool:
    pg = sec.get("page_number")
    if pg is None:
        return True
    sec_id = str(sec.get("section_id") or "")
    peer_pages = [
        int(s.get("page_number"))
        for s in chapter.get("sections") or []
        if s.get("page_number") is not None and str(s.get("section_id") or "") != sec_id
    ]
    if not peer_pages:
        return True
    return min(peer_pages) - margin <= int(pg) <= max(peer_pages) + margin


def _reassign_preserves_page_order(
    sec: Dict[str, Any],
    from_ch: Dict[str, Any],
    to_ch: Dict[str, Any],
    *,
    margin: int,
) -> bool:
    pg = sec.get("page_number")
    if pg is None:
        return True
    to_pages = _chapter_page_numbers(to_ch)
    if to_pages and int(pg) < min(to_pages) - margin:
        return False
    from_pages = _chapter_page_numbers(from_ch)
    sec_id = str(sec.get("section_id") or "")
    from_peer_pages = [
        int(s.get("page_number"))
        for s in from_ch.get("sections") or []
        if s.get("page_number") is not None and str(s.get("section_id") or "") != sec_id
    ]
    if from_peer_pages and int(pg) < min(from_peer_pages) - margin:
        if to_pages and min(to_pages) > min(from_peer_pages):
            return False
    return True


def _sort_chapter_sections(chapters: List[Dict[str, Any]]) -> None:
    for ch in chapters:
        ch["sections"] = sorted(
            list(ch.get("sections") or []),
            key=lambda s: (s.get("page_number") or 0, str(s.get("section_id") or "")),
        )


def rebalance_sections_by_page_order(chapters: List[Dict[str, Any]]) -> int:
    """Move sections whose page number is far outside their chapter's page span."""
    margin = int(getattr(config, "CHAPTER_PLACEMENT_PAGE_MARGIN", 8) or 8)
    moved = 0
    for ci, ch in enumerate(chapters):
        for si, sec in list(enumerate(ch.get("sections") or [])):
            if _section_page_fits_chapter(sec, ch, margin=margin):
                continue
            pg = sec.get("page_number")
            if pg is None:
                continue
            best_j = ci
            best_dist = float("inf")
            for j, other in enumerate(chapters):
                pages = _chapter_page_numbers(other)
                if not pages:
                    continue
                if min(pages) - margin <= int(pg) <= max(pages) + margin:
                    best_j = j
                    best_dist = 0.0
                    break
                dist = min(abs(int(pg) - min(pages)), abs(int(pg) - max(pages)))
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
            if best_j != ci:
                ch["sections"].pop(si)
                chapters[best_j]["sections"].append(dict(sec))
                moved += 1
                break
    _sort_chapter_sections(chapters)
    chapters[:] = [ch for ch in chapters if ch.get("sections")]
    return moved


def universal_clean_heading(
    heading: str,
    *,
    subheadings: Optional[Sequence[Dict[str, Any]]] = None,
    page_number: Optional[int] = None,
    parent_heading: str = "",
    preview: str = "",
    use_transformers: bool = False,
) -> str:
    """Rule-based title cleanup; optional MiniLM when use_transformers=True."""
    from src.modules.structure.final_structuring.heading_cleanup import _rule_clean_heading

    raw = _norm(heading)
    if not raw:
        return raw

    subs = list(subheadings or [])
    cleaned = _rule_clean_heading(raw, subheadings=subs)

    if use_transformers and is_weak_section_heading(cleaned):
        sub_titles = [_norm(str(s.get("heading") or "")) for s in subs]
        from src.modules.structure.final_structuring.models.mini_lm_title_pick import mini_lm_pick_title

        threshold = float(getattr(config, "HEADING_CLEANUP_MINILM_PICK_THRESHOLD", 0.82) or 0.82)
        picked = mini_lm_pick_title(cleaned, subheadings=sub_titles, threshold=threshold)
        if picked:
            cleaned = picked

    if is_weak_section_heading(cleaned):
        from_sub = title_from_subheadings(subs)
        if from_sub and not is_weak_section_heading(from_sub):
            cleaned = from_sub

    english = filter_english_heading(cleaned) or cleaned
    english = _BULLET_PREFIX.sub("", english).strip()
    if _norm(english).lower().startswith("definition"):
        rest = re.sub(r"^definition\s*[—\-:]\s*", "", english, flags=re.I).strip()
        if rest and rest.lower() != english.lower():
            english = f"Definition — {rest}"

    if is_weak_section_heading(english):
        if preview:
            from src.modules.structure.final_structuring.heading_title_engine import title_from_fragment_preview

            frag_title = title_from_fragment_preview({"fragment": {"preview": preview}})
            if frag_title:
                english = frag_title
        if is_weak_section_heading(english) and page_number:
            english = f"Section topic (p. {page_number})"

    return english[:120]


def _section_labels(sec: Dict[str, Any]) -> List[str]:
    labels = [_norm(str(sec.get("heading") or ""))]
    for sub in sec.get("subheadings") or []:
        h = _norm(str(sub.get("heading") or ""))
        if h and not is_weak_section_heading(h):
            labels.append(h)
    return [x for x in labels if x]


def _section_embedding_text(sec: Dict[str, Any]) -> str:
    parts = _section_labels(sec)
    frag = sec.get("fragment") or {}
    preview = _norm(str(frag.get("preview") or ""))[:200]
    if preview:
        parts.append(preview)
    return " — ".join(parts)[:400]


def _flatten_sections(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for ch in chapters:
        for sec in ch.get("sections") or []:
            flat.append(dict(sec))
    return flat


_MODULE_LINE_RE = re.compile(r"^\s*(module|unit)\s+(\d+)\s*:?\s*$", re.I)


def detect_module_unit_break_pages_from_lines(
    lines: Optional[Sequence[Any]],
) -> List[Dict[str, Any]]:
    """Find MODULE/UNIT partition pages from layout lines (syllabus-style PDFs)."""
    if not lines:
        return []
    out: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ln in lines:
        text = str(getattr(ln, "text", None) or (ln.get("text") if isinstance(ln, dict) else "") or "").strip()
        m = _MODULE_LINE_RE.match(text)
        if not m:
            continue
        kind, num = m.group(1).lower(), m.group(2)
        key = (kind, num)
        if key in seen:
            continue
        seen.add(key)
        page = getattr(ln, "page_number", None)
        if page is None and isinstance(ln, dict):
            page = ln.get("page_number") or ln.get("page")
        if page is None:
            continue
        out.append({"page": int(page), "label": text, "kind": kind, "number": num})
    return sorted(out, key=lambda x: int(x["page"]))


def split_chapters_at_module_page_markers(
    chapters: List[Dict[str, Any]],
    module_breaks: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Split flat sections when MODULE/UNIT lines appear mid-document (page order)."""
    if not module_breaks:
        return chapters, 0
    sections = _flatten_sections(chapters)
    if len(sections) < 2:
        return chapters, 0

    ordered_breaks = sorted(
        [b for b in module_breaks if b.get("page") is not None and int(b["page"]) > 0],
        key=lambda b: int(b["page"]),
    )
    if len(ordered_breaks) < 2:
        return chapters, 0

    def _module_bucket(page: Any) -> int:
        if page is None:
            return 0
        idx = 0
        for i, br in enumerate(ordered_breaks):
            if int(page) >= int(br["page"]):
                idx = i
        return idx

    buckets: Dict[int, List[Dict[str, Any]]] = {}
    for sec in sorted(sections, key=lambda s: int(s.get("page_number") or 0)):
        buckets.setdefault(_module_bucket(sec.get("page_number")), []).append(sec)

    bucket_keys = sorted(buckets.keys())
    chunks = [buckets[k] for k in bucket_keys if buckets[k]]
    if len(chunks) <= 1:
        return chapters, 0

    from src.modules.structure.dropped_heading_registry import partition_heading_to_study_title

    book_title = ""
    new_chapters: List[Dict[str, Any]] = []
    for key, chunk in zip(bucket_keys, chunks):
        label = str(ordered_breaks[key].get("label") or "") if key < len(ordered_breaks) else ""
        title = infer_chapter_title_from_sections(chunk, book_title=book_title)
        module_title = partition_heading_to_study_title(label) if label else ""
        if module_title and (
            not title
            or len(title) < 10
            or title.lower().startswith("study topic")
            or title.lower().startswith("section topic")
        ):
            title = module_title
        elif module_title and label:
            title = f"{module_title} — {title}"[:120] if title and title != module_title else module_title
        new_chapters.append(
            {
                "chapter_id": f"C{len(new_chapters) + 1}",
                "heading": (title or module_title or "Chapter")[:120],
                "level": 1,
                "page_start": chunk[0].get("page_number"),
                "page_end": chunk[-1].get("page_number"),
                "sections": chunk,
                "assignment_method": "15h_module_page_split",
                "module_page_partition": True,
            }
        )
    return _renumber_chapters(new_chapters), len(new_chapters) - len(chapters)


def _renumber_chapters(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for i, ch in enumerate(chapters, start=1):
        ch["chapter_id"] = f"C{i}"
        if ch.get("sections"):
            pg_start = ch["sections"][0].get("page_number")
            pg_end = ch["sections"][-1].get("page_number")
            if pg_start is not None:
                ch["page_start"] = pg_start
            if pg_end is not None:
                ch["page_end"] = pg_end
    return chapters


def split_chapters_at_structural_markers(chapters: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Split when MODULE/UNIT/major headings appear mid-chapter."""
    sections = _flatten_sections(chapters)
    if not sections:
        return chapters, 0

    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []

    structural_breaks = 0
    for sec in sections:
        if current and section_starts_new_part(sec):
            chunks.append(current)
            current = [sec]
            structural_breaks += 1
        else:
            current.append(sec)
    if current:
        chunks.append(current)

    if structural_breaks == 0 or len(chunks) <= 1:
        return chapters, 0

    new_chapters: List[Dict[str, Any]] = []
    for chunk in chunks:
        if not chunk:
            continue
        title = infer_chapter_title_from_sections(chunk)
        new_chapters.append(
            {
                "chapter_id": f"C{len(new_chapters) + 1}",
                "heading": title[:120],
                "level": 1,
                "page_start": chunk[0].get("page_number"),
                "page_end": chunk[-1].get("page_number"),
                "sections": chunk,
                "assignment_method": "15h_split",
            }
        )
    return _renumber_chapters(new_chapters), len(new_chapters) - len(chapters)


def split_oversized_chapters(chapters: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Split chapters that exceed the configured section budget at natural boundaries."""
    max_sections = int(
        getattr(config, "CHAPTER_PLACEMENT_MAX_SECTIONS_PER_CHAPTER", 10) or 10
    )
    page_gap = int(getattr(config, "CHAPTER_PLACEMENT_PAGE_GAP_SPLIT", 12) or 12)
    out: List[Dict[str, Any]] = []
    extra = 0

    for ch in chapters:
        sections = list(ch.get("sections") or [])
        if len(sections) <= max_sections:
            out.append(ch)
            continue

        split_at: List[int] = []
        for i in range(1, len(sections)):
            if section_starts_new_part(sections[i]):
                split_at.append(i)
                continue
            prev_pg = sections[i - 1].get("page_number")
            cur_pg = sections[i].get("page_number")
            if prev_pg is not None and cur_pg is not None and int(cur_pg) - int(prev_pg) >= page_gap:
                split_at.append(i)

        if not split_at:
            split_at = list(range(max_sections, len(sections), max_sections))

        bounds = [0] + sorted(set(split_at)) + [len(sections)]
        for start, end in zip(bounds, bounds[1:]):
            chunk = sections[start:end]
            if not chunk:
                continue
            title = infer_chapter_title_from_sections(chunk) or str(ch.get("heading") or "Chapter")
            out.append(
                {
                    "chapter_id": f"C{len(out) + 1}",
                    "heading": title[:120],
                    "level": 1,
                    "page_start": chunk[0].get("page_number"),
                    "page_end": chunk[-1].get("page_number"),
                    "sections": chunk,
                    "assignment_method": "15h_size_split",
                }
            )
        extra += max(0, len(bounds) - 2)

    if extra <= 0:
        return chapters, 0
    return _renumber_chapters(out), extra


def _chapter_centroids(
    chapters: List[Dict[str, Any]],
    encoder: Any,
) -> List[Optional[np.ndarray]]:
    centroids: List[Optional[np.ndarray]] = []
    for ch in chapters:
        texts = [_section_embedding_text(s) for s in ch.get("sections") or []]
        texts = [t for t in texts if t.strip()]
        if not texts:
            centroids.append(None)
            continue
        emb = encoder.encode(texts)
        if emb is None or len(emb) == 0:
            centroids.append(None)
        else:
            centroids.append(np.mean(emb, axis=0))
    return centroids


def reassign_outlier_sections(
    chapters: List[Dict[str, Any]],
    *,
    margin: float = 0.06,
) -> int:
    """Move sections whose embeddings fit a neighbouring chapter better (MiniLM)."""
    from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

    encoder = get_mini_lm_encoder()
    if len(chapters) < 2:
        return 0

    page_margin = int(getattr(config, "CHAPTER_PLACEMENT_PAGE_MARGIN", 8) or 8)
    moved = 0
    max_passes = 2
    for _ in range(max_passes):
        centroids = _chapter_centroids(chapters, encoder)
        pass_moved = 0
        for ci, ch in enumerate(chapters):
            for si, sec in enumerate(list(ch.get("sections") or [])):
                text = _section_embedding_text(sec)
                if not text:
                    continue
                sec_emb = encoder.encode([text])
                if sec_emb is None or centroids[ci] is None:
                    continue
                own_sim = float(np.dot(sec_emb[0], centroids[ci]))
                best_j = ci
                best_sim = own_sim
                for j, cen in enumerate(centroids):
                    if j == ci or cen is None:
                        continue
                    sim = float(np.dot(sec_emb[0], cen))
                    if sim > best_sim:
                        best_sim = sim
                        best_j = j
                if best_j != ci and (best_sim - own_sim) >= margin and abs(best_j - ci) == 1:
                    if not _reassign_preserves_page_order(
                        sec, ch, chapters[best_j], margin=page_margin
                    ):
                        continue
                    sec_copy = dict(sec)
                    ch["sections"].pop(si)
                    chapters[best_j]["sections"].append(sec_copy)
                    pass_moved += 1
                    break
            if pass_moved:
                break
        moved += pass_moved
        if not pass_moved:
            break

    for ch in chapters:
        ch["sections"] = [s for s in ch.get("sections") or [] if s]
    chapters[:] = [ch for ch in chapters if ch.get("sections")]
    _renumber_chapters(chapters)
    return moved


def _section_heading_candidates(sections: Sequence[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for sec in sections:
        h = _norm(str(sec.get("heading") or ""))
        if h and not is_weak_section_heading(h) and not is_structural_chapter_break(h):
            key = normalize_heading(h)
            if key not in seen:
                seen.add(key)
                out.append(h)
    return out


def infer_chapter_title_from_sections(
    sections: Sequence[Dict[str, Any]],
    *,
    book_title: str = "",
) -> str:
    """Pick a chapter title from its sections — rules + MiniLM + optional cloud fallback."""
    from src.modules.structure.final_structuring.heading_title_engine import pick_chapter_title

    return pick_chapter_title(sections, book_title=book_title)


def _chapter_heading_cohesion(chapter: Dict[str, Any], encoder: Any) -> float:
    sections = list(chapter.get("sections") or [])
    if len(sections) < 2:
        return 1.0
    title = _norm(str(chapter.get("heading") or ""))
    labels = [_norm(str(s.get("heading") or "")) for s in sections if _norm(str(s.get("heading") or ""))]
    if not title or not labels:
        return 1.0
    title_emb = encoder.encode([title])
    label_emb = encoder.encode(labels)
    if title_emb is None or label_emb is None:
        return 1.0
    sims = label_emb @ title_emb[0]
    return float(np.median(sims))


def refine_broad_chapter_titles(chapters: List[Dict[str, Any]]) -> int:
    """Rename chapters when the title is too narrow for the sections grouped under it."""
    from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

    encoder = get_mini_lm_encoder()
    min_sections = int(getattr(config, "CHAPTER_PLACEMENT_MIN_SECTIONS_FOR_RENAME", 3) or 3)
    cohesion_threshold = float(getattr(config, "CHAPTER_PLACEMENT_COHESION_THRESHOLD", 0.58) or 0.58)
    changed = 0

    for ch in chapters:
        sections = list(ch.get("sections") or [])
        if len(sections) < min_sections:
            continue
        ch_title = _norm(str(ch.get("heading") or ""))
        first_title = _norm(str(sections[0].get("heading") or ""))
        cohesion = _chapter_heading_cohesion(ch, encoder)
        title_is_first_only = normalize_heading(ch_title) == normalize_heading(first_title)
        if not title_is_first_only and cohesion >= cohesion_threshold:
            continue

        new_title = infer_chapter_title_from_sections(sections)
        if new_title and normalize_heading(new_title) != normalize_heading(ch_title):
            ch["heading"] = new_title[:120]
            changed += 1

    return changed


def apply_universal_heading_cleanup(
    hierarchy: Dict[str, Any],
    *,
    use_transformers: bool = True,
) -> int:
    """Clean all section/chapter/subheading titles without book-specific aliases."""
    changed = 0
    for ch in hierarchy.get("chapters") or []:
        ch_name = _norm(str(ch.get("heading") or ""))
        new_ch = universal_clean_heading(ch_name, use_transformers=use_transformers)
        if new_ch != ch_name:
            ch["heading"] = new_ch
            changed += 1
            ch_name = new_ch
        for sec in ch.get("sections") or []:
            old = _norm(str(sec.get("heading") or ""))
            new = universal_clean_heading(
                old,
                subheadings=sec.get("subheadings"),
                page_number=sec.get("page_number"),
                parent_heading=ch_name,
                use_transformers=use_transformers,
            )
            if new != old:
                sec["heading"] = new
                changed += 1
    return changed


def enforce_chapter_structure(hierarchy: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """
    Final hierarchy pass after 15j/15g: split oversized chapters, fix mirrors, repair prose titles.
    Prevents syllabus books from collapsing to a single mega-chapter.
    """
    from src.modules.structure.final_structuring.heading_cleanup import (
        disambiguate_duplicate_section_headings,
        sanitize_hierarchy_headings,
    )
    from src.modules.structure.final_structuring.subheading_refinement import (
        fix_parent_mirror_chapters,
        fix_unacceptable_section_titles,
        fix_verbose_section_titles,
    )

    out = hierarchy
    chapters = list(out.get("chapters") or [])
    if not chapters:
        return out, {}

    chapters, struct_splits = split_chapters_at_structural_markers(chapters)
    chapters, size_splits = split_oversized_chapters(chapters)
    out["chapters"] = chapters

    stats: Dict[str, int] = {
        "structural_splits": struct_splits,
        "size_splits": size_splits,
        "mirror_fixes": fix_parent_mirror_chapters(out),
        "sanitize_headings": sanitize_hierarchy_headings(out),
        "verbose_title_fixes": fix_verbose_section_titles(out),
        "unacceptable_title_fixes": fix_unacceptable_section_titles(out, use_transformers=False),
    }
    disambiguate_duplicate_section_headings(list(out.get("chapters") or []))

    chapters = list(out.get("chapters") or [])
    chapters, final_splits = split_oversized_chapters(chapters)
    out["chapters"] = _renumber_chapters(chapters)
    _sort_chapter_sections(out["chapters"])
    stats["final_size_splits"] = final_splits

    meta = dict(out.get("meta") or {})
    meta["total_chapters"] = len(out["chapters"])
    meta["total_sections"] = sum(len(c.get("sections") or []) for c in out["chapters"])
    meta["enforce_chapter_structure"] = stats
    out["meta"] = meta
    logger.info(
        "enforce_chapter_structure: chapters=%s size_splits=%s mirror=%s title_fixes=%s",
        meta["total_chapters"],
        size_splits + final_splits,
        stats["mirror_fixes"],
        stats["unacceptable_title_fixes"],
    )
    return out, stats


def refresh_chapter_placement_if_module_gap(
    chapter_hierarchy: Dict[str, Any],
    lines: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Re-run 15h when MODULE/UNIT markers imply more chapters than we have."""
    breaks = detect_module_unit_break_pages_from_lines(lines)
    chapter_count = len(chapter_hierarchy.get("chapters") or [])
    if len(breaks) >= 2 and chapter_count < len(breaks):
        return run_chapter_placement(chapter_hierarchy, lines=lines)
    return chapter_hierarchy


def run_chapter_placement(
    chapter_hierarchy: Dict[str, Any],
    *,
    lines: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Stage 15h — structural splits, MiniLM reassignment, chapter title inference."""
    if not getattr(config, "CHAPTER_PLACEMENT_ENABLED", True):
        return chapter_hierarchy

    out = copy.deepcopy(chapter_hierarchy)
    chapters = list(out.get("chapters") or [])
    if not chapters:
        return out

    meta = dict(out.get("meta") or {})
    splits = size_splits = reassigns = page_rebalance = module_splits = 0

    module_breaks = detect_module_unit_break_pages_from_lines(lines)
    if module_breaks:
        chapters, module_splits = split_chapters_at_module_page_markers(chapters, module_breaks)

    chapters, splits = split_chapters_at_structural_markers(chapters)
    chapters, size_splits = split_oversized_chapters(chapters)
    splits += size_splits
    page_rebalance = rebalance_sections_by_page_order(chapters)
    if getattr(config, "CHAPTER_PLACEMENT_REASSIGN", True):
        margin = float(getattr(config, "CHAPTER_PLACEMENT_REASSIGN_MARGIN", 0.06) or 0.06)
        reassigns = reassign_outlier_sections(chapters, margin=margin)
        page_rebalance += rebalance_sections_by_page_order(chapters)

    from src.modules.structure.final_structuring.chapter_cohesion import consolidate_chapter_hierarchy

    min_secs = int(getattr(config, "CHAPTER_PLACEMENT_MIN_SECTIONS_PER_CHAPTER", 3) or 3)
    min_chars = int(getattr(config, "CHAPTER_PLACEMENT_MIN_CHAPTER_CHARS", 400) or 400)
    chapters, merge_stats = consolidate_chapter_hierarchy(
        chapters,
        min_sections=min_secs,
        min_chars=min_chars,
    )
    merge_count = int(merge_stats.get("tiny_merged", 0)) + int(merge_stats.get("related_merged", 0))

    out["chapters"] = _renumber_chapters(chapters)
    _sort_chapter_sections(out["chapters"])
    meta.update(
        {
            "total_chapters": len(out["chapters"]),
            "total_sections": sum(len(c.get("sections") or []) for c in out["chapters"]),
            "chapter_placement_method": "structural+minilm",
            "chapter_placement_module_splits": module_splits,
            "chapter_placement_splits": splits,
            "chapter_placement_reassignments": reassigns,
            "chapter_placement_page_rebalances": page_rebalance,
            "chapter_placement_merged": merge_count,
            "chapter_placement_related_merged": merge_stats.get("related_merged", 0),
        }
    )
    out["meta"] = meta
    logger.info(
        "15h chapter placement: splits=%s reassigns=%s page_rebalances=%s",
        splits,
        reassigns,
        page_rebalance,
    )
    return out

"""Stages 15a/15c/15d/16 — heading hierarchy, ultimate sections, final book, RAG snapshot."""

from __future__ import annotations

import hashlib
import re

import numpy as np
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.shared import config
from src.shared.models import NormalizedLine
from src.modules.structure.final_structuring.models.mini_lm_encoder import get_mini_lm_encoder

_CHAPTER_RE = re.compile(r"^\s*chapter\s+\d+", re.IGNORECASE)
_ROMAN_MAJOR_RE = re.compile(r"^\s*[IVXLC]+\.\s+[A-Z]")
_LETTER_SECTION_RE = re.compile(r"^\s*[A-H]\.\s+", re.IGNORECASE)
_NUMBERED_SUB_RE = re.compile(r"^\s*\(\d+\)\s+|\(\s*[a-z]\s*\)\s+|\d+\.\s+")
_SEE_ABOVE_RE = re.compile(r"\(\s*-\s*see above\s*-\s*\)", re.IGNORECASE)
_PREAMBLE_CLAUSE_RE = re.compile(r";\s*$")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _pattern_level(text: str) -> Optional[Tuple[int, str]]:
    t = _norm(text)
    if not t:
        return None
    if _CHAPTER_RE.match(t):
        return 1, "pattern"
    if _ROMAN_MAJOR_RE.match(t):
        return 1, "pattern"
    if _LETTER_SECTION_RE.match(t):
        return 2, "pattern"
    if _NUMBERED_SUB_RE.match(t):
        return 2, "pattern"
    letters = re.sub(r"[^A-Za-z]", "", t)
    if letters.isupper() and len(letters) >= 8 and len(t.split()) >= 2:
        return 1, "pattern"
    return None


def _looks_like_parent_heading(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    if _CHAPTER_RE.match(t) or _ROMAN_MAJOR_RE.match(t):
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    if letters.isupper() and len(letters) >= 10:
        return True
    if re.match(r"^[A-Z]\.\s+[A-Z]", t):
        return True
    if re.match(r"^\d{1,2}\.\s+[A-Z]", t):
        return True
    return False


def _looks_like_structural_heading(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    if _looks_like_parent_heading(t):
        return True
    if re.match(r"^[A-Z]\.\s+[A-Z]", t):
        return True
    if re.match(r"^\d{1,2}\.\s+[A-Z]", t):
        return True
    return False


def _line_text_by_id(lines: Sequence[NormalizedLine]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if isinstance(lid, int):
            out[lid] = getattr(ln, "text", "") or ""
    return out


def _span_for_heading(
    line_id: int,
    next_line_id: Optional[int],
    line_text: Dict[int, str],
) -> Tuple[int, int, str]:
    start = line_id + 1
    end = (next_line_id - 1) if isinstance(next_line_id, int) else max(line_text.keys(), default=line_id)
    if end < start:
        end = start - 1
    parts: List[str] = []
    for lid in range(start, end + 1):
        t = (line_text.get(lid) or "").strip()
        if t:
            parts.append(t)
    text = "\n".join(parts).strip()
    return start, end, text


def build_heading_hierarchy(
    headings: Sequence[Dict[str, Any]],
    *,
    lines: Sequence[NormalizedLine],
) -> List[Dict[str, Any]]:
    """Stage 15a — assign refined heading levels."""
    mini_lm = get_mini_lm_encoder()
    texts = [_norm(h.get("text") or "") for h in headings]
    embs = mini_lm.encode([t for t in texts if t]) if texts else None
    emb_idx = 0
    per_emb: List[Any] = []
    for t in texts:
        if t and embs is not None and len(embs) > emb_idx:
            per_emb.append(embs[emb_idx])
            emb_idx += 1
        else:
            per_emb.append(None)

    out: List[Dict[str, Any]] = []
    prev_emb = None
    for i, h in enumerate(headings):
        text = _norm(h.get("text") or "")
        lid = h.get("line_id")
        pat = _pattern_level(text)
        if pat:
            level, method = pat
        elif embs is not None and per_emb[i] is not None and prev_emb is not None:
            sim = float(np.dot(per_emb[i], prev_emb))
            if sim >= 0.72:
                level, method = 2, "miniLM_cluster"
            else:
                level, method = 2, "fallback"
        else:
            level, method = 2, "fallback"
        if per_emb[i] is not None:
            prev_emb = per_emb[i]
        out.append(
            {
                "line_id": lid,
                "text": h.get("text") or text,
                "level": level,
                "level_method": method,
                "page_number": h.get("page_number"),
            }
        )
    return out


def _fragment_span_by_heading(
    headings_with_levels: List[Dict[str, Any]],
    fragments: Sequence[Dict[str, Any]],
) -> Dict[int, Dict[str, int]]:
    out: Dict[int, Dict[str, int]] = {}
    for frag in fragments:
        heading_text = _norm(str(frag.get("heading_text") or ""))
        start = frag.get("start_line")
        end = frag.get("end_line")
        if not heading_text or start is None or end is None:
            continue
        for h in headings_with_levels:
            if _norm(str(h.get("text") or "")) == heading_text:
                lid = h.get("line_id")
                if isinstance(lid, int):
                    out[lid] = {"start_line": int(start), "end_line": int(end), "chars": int(frag.get("fragment_chars") or 0)}
                break
    return out


def build_ultimate_sections(
    *,
    headings: Sequence[Dict[str, Any]],
    hierarchy: Sequence[Dict[str, Any]],
    lines: Sequence[NormalizedLine],
    fragments: Sequence[Dict[str, Any]],
    metadata_line_ids: Set[int],
    toc_seed_ids: Set[int],
) -> Dict[str, Any]:
    """Stage 15d — parent-first sections with optional one-level children."""
    level_by_id = {int(h["line_id"]): int(h.get("level") or 2) for h in hierarchy if isinstance(h.get("line_id"), int)}
    line_text = _line_text_by_id(lines)
    sorted_heads = sorted(
        [h for h in headings if isinstance(h.get("line_id"), int)],
        key=lambda x: int(x["line_id"]),
    )
    next_id_by_line = {}
    for i, h in enumerate(sorted_heads):
        lid = int(h["line_id"])
        nxt = int(sorted_heads[i + 1]["line_id"]) if i + 1 < len(sorted_heads) else None
        next_id_by_line[lid] = nxt

    thresholds = config.resolve_ultimate_thresholds()
    min_parent_chars = int(thresholds["min_parent_fragment_chars"])
    min_nested_chars = int(thresholds["min_section_chars_for_nesting"])
    min_heading_fragment_chars = int(thresholds["min_heading_fragment_chars"])
    max_rewrite_section_chars = int(thresholds["max_rewrite_section_chars"])
    profile = str(thresholds.get("profile") or "medium")

    headings_with_levels: List[Dict[str, Any]] = []
    for h in sorted_heads:
        lid = int(h["line_id"])
        if lid in metadata_line_ids:
            continue
        text = _norm(h.get("text") or "")
        start, end, body = _span_for_heading(lid, next_id_by_line.get(lid), line_text)
        headings_with_levels.append(
            {
                **h,
                "text": text,
                "line_id": lid,
                "level": level_by_id.get(lid, 2),
                "start_line": start,
                "end_line": end,
                "body": body,
                "body_chars": len(body),
            }
        )

    def _is_high_probability_row(row: Dict[str, Any]) -> bool:
        text = str(row.get("text") or "")
        body_chars = int(row.get("body_chars") or 0)
        if _SEE_ABOVE_RE.search(text):
            return False
        if _looks_like_structural_heading(text):
            return body_chars >= min_heading_fragment_chars or int(row.get("level") or 2) == 1
        if body_chars >= min_heading_fragment_chars:
            return True
        if _PREAMBLE_CLAUSE_RE.search(text):
            return False
        return False

    kept_rows = [r for r in headings_with_levels if _is_high_probability_row(r)]
    dropped_count = len(headings_with_levels) - len(kept_rows)

    sections: List[Dict[str, Any]] = []
    sec_no = 0
    current: Optional[Dict[str, Any]] = None

    def _fragment_payload(row: Dict[str, Any]) -> Dict[str, Any]:
        body = str(row.get("body") or "")
        if len(body) > max_rewrite_section_chars:
            body = body[:max_rewrite_section_chars].rstrip()
        preview = body[:160]
        return {
            "start_line": row.get("start_line"),
            "end_line": row.get("end_line"),
            "chars": len(body),
            "preview": preview,
        }

    def _flush_section() -> None:
        nonlocal current
        if current is not None:
            sections.append(current)
            current = None

    for row in kept_rows:
        level = int(row.get("level") or 2)
        body_chars = int(row.get("body_chars") or 0)
        text = str(row.get("text") or "")
        structural = _looks_like_structural_heading(text) or level == 1
        as_section = (
            current is None
            or (structural and body_chars >= min_heading_fragment_chars)
            or body_chars >= min_parent_chars
        )
        if as_section:
            _flush_section()
            sec_no += 1
            current = {
                "section_id": f"S{sec_no}",
                "heading": text,
                "line_id": row["line_id"],
                "page_number": row.get("page_number"),
                "fragment": _fragment_payload(row),
                "subheadings": [],
            }
            continue
        if current is not None and body_chars >= min_nested_chars:
            current["subheadings"].append(
                {
                    "heading": text,
                    "line_id": row["line_id"],
                    "page_number": row.get("page_number"),
                    "fragment": _fragment_payload(row),
                }
            )
            continue
        if current is not None and body_chars > 0:
            current["subheadings"].append(
                {
                    "heading": text,
                    "line_id": row["line_id"],
                    "page_number": row.get("page_number"),
                    "fragment": _fragment_payload(row),
                }
            )
            continue
        # Too small to stand alone — fold into current section body metadata only
        if current is not None:
            current["subheadings"].append(
                {
                    "heading": text,
                    "line_id": row["line_id"],
                    "page_number": row.get("page_number"),
                    "fragment": _fragment_payload(row),
                }
            )
    _flush_section()

    sub_count = sum(len(s.get("subheadings") or []) for s in sections)
    return {
        "meta": {
            "strategy": "single_level_parents_with_optional_one_level_children",
            "threshold_profile": profile,
            "thresholds": {
                "min_parent_fragment_chars": min_parent_chars,
                "min_section_chars_for_nesting": min_nested_chars,
                "min_heading_fragment_chars": min_heading_fragment_chars,
                "max_rewrite_section_chars": max_rewrite_section_chars,
            },
            "input_heading_count": len(headings),
            "kept_heading_count": len(kept_rows),
            "dropped_heading_count": dropped_count,
            "total_sections": len(sections),
            "total_subheadings": sub_count,
            "metadata_line_count": len(metadata_line_ids),
            "toc_seed_count": len(toc_seed_ids),
        },
        "toc": {"seed_headings": []},
        "metadata": {"line_ids": sorted(metadata_line_ids)},
        "sections": sections,
    }


def assemble_final_book(
    *,
    book_title: str,
    first_toc_page: int,
    is_doubted: bool,
    ultimate_sections: Dict[str, Any],
    chapter_hierarchy: Optional[Dict[str, Any]] = None,
    metadata_line_ids: Set[int],
    doubted_segments: Optional[List[Dict[str, Any]]] = None,
    total_headings: int = 0,
) -> Dict[str, Any]:
    """Stage 15c — consolidated book payload with optional 15e chapter tree."""
    if chapter_hierarchy and chapter_hierarchy.get("chapters"):
        chapters = list(chapter_hierarchy.get("chapters") or [])
        topic_count = sum(
            1 + len(s.get("subheadings") or []) for ch in chapters for s in ch.get("sections") or []
        )
    else:
        sections = list(ultimate_sections.get("sections") or [])
        chapters = []
        topic_count = 0
        for sec in sections:
            topics = [
                {
                    "topic_id": f"{sec['section_id']}_T1",
                    "heading": sec.get("heading"),
                    "line_id": sec.get("line_id"),
                    "page_number": sec.get("page_number"),
                    "level": 2,
                }
            ]
            for j, sub in enumerate(sec.get("subheadings") or [], start=2):
                topics.append(
                    {
                        "topic_id": f"{sec['section_id']}_T{j}",
                        "heading": sub.get("heading"),
                        "line_id": sub.get("line_id"),
                        "page_number": sub.get("page_number"),
                        "level": 3,
                    }
                )
            topic_count += len(topics)
            chapters.append(
                {
                    "chapter_id": sec.get("section_id"),
                    "level": 1,
                    "heading": sec.get("heading"),
                    "page_start": sec.get("page_number"),
                    "page_end": sec.get("page_number"),
                    "line_id": sec.get("line_id"),
                    "sections": [{**sec, "level": 2, "subheadings": [{**sub, "level": 3} for sub in sec.get("subheadings") or []]}],
                    "topics": topics,
                }
            )
    return {
        "book_title": book_title,
        "is_doubted": is_doubted,
        "first_toc_page": first_toc_page,
        "ultimate_sections": ultimate_sections,
        "chapter_hierarchy": chapter_hierarchy or {},
        "chapters": chapters,
        "toc": ultimate_sections.get("toc") or {"seed_headings": []},
        "metadata": ultimate_sections.get("metadata") or {"line_ids": sorted(metadata_line_ids)},
        "doubted_segments": doubted_segments or [],
        "stats": {
            "total_chapters": len(chapters),
            "total_topics": topic_count,
            "total_headings": total_headings,
            "total_visual_tables": 0,
            "total_visual_images": 0,
            "doubted_segments_resolved": len(doubted_segments or []),
            "doubted_as_real_content": 0,
            "doubted_as_metadata": 0,
            "doubted_as_toc": 0,
            "doubted_uncertain": 0,
        },
    }


def _token_estimate(text: str) -> int:
    return max(1, len(text.split()))


def _quality_score(char_count: int, heading_words: int) -> float:
    base = min(1.0, char_count / 1200.0)
    return round(0.15 + (0.55 * base) + min(0.2, heading_words * 0.02), 4)


def build_rag_snapshot(
    *,
    book_title: str,
    run_id: str,
    ultimate_sections: Dict[str, Any],
    metadata_line_ids: Set[int],
) -> Dict[str, Any]:
    """Stage 16 — rewrite-ready chunks and plans."""
    chunks: List[Dict[str, Any]] = []
    rewrite_plans: List[Dict[str, Any]] = []
    chunk_no = 0
    for sec in ultimate_sections.get("sections") or []:
        for target in [sec, *(sec.get("subheadings") or [])]:
            heading = str(target.get("heading") or "").strip()
            if not heading:
                continue
            frag = target.get("fragment") or {}
            text = str(frag.get("preview") or heading)
            if frag.get("chars") and int(frag["chars"]) > len(text):
                text = text  # preview only in snapshot when full body not stored
            chunk_no += 1
            lid = target.get("line_id")
            char_count = int(frag.get("chars") or len(text))
            chunks.append(
                {
                    "chunk_id": f"RC{chunk_no:05d}",
                    "book_title": book_title,
                    "run_id": run_id,
                    "section_id": sec.get("section_id"),
                    "part_no": 1,
                    "heading": heading,
                    "line_id": lid,
                    "page_number": target.get("page_number"),
                    "start_line": frag.get("start_line"),
                    "end_line": frag.get("end_line"),
                    "text": text,
                    "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "char_count": char_count,
                    "token_estimate": _token_estimate(text),
                    "quality_score": _quality_score(char_count, len(heading.split())),
                    "index_priority": round(min(0.95, 0.65 + min(0.25, char_count / 5000.0)), 4),
                    "is_metadata": isinstance(lid, int) and lid in metadata_line_ids,
                    "is_toc": False,
                    "indexable": True,
                }
            )
            rewrite_plans.append(
                {
                    "parent_heading": heading,
                    "goal": f"Rewrite section '{heading}' with complete and coherent structure.",
                    "mandatory_subpoints": [],
                    "optional_enrichments": [],
                    "order_constraints": [],
                }
            )
    return {
        "book_title": book_title,
        "run_id": run_id,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "concept_map": {"nodes": [], "edges": []},
        "rewrite_plans": rewrite_plans,
    }

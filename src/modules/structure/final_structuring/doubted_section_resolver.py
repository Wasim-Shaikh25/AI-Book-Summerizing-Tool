"""
Stage 15b — Doubted Section Resolver

Segregates doubted lines into: real_content | toc | metadata | uncertain

Decision chain per segment:
  0. Structural rules (before first chapter, scattered TOC seeds, syllabus block)
  1. Strong deterministic signals → classify immediately
  2. Optional local LLM (Ollama / llama.cpp GGUF) or legacy BigBird embeddings
  3. all-MiniLM heading similarity vs. confirmed headings (chapter body only)
  4. ms-marco (heading, body) coherence for remaining uncertain

Configure via ``.env``:
  - ``DOUBTED_RESOLVER_MODE``: fast | revalidate_selected (default)
  - ``DOUBTED_RESOLVER_LLM``: off | bigbird | or auto from ``LLM_PROVIDER``
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from .signal_extractor import compute_line_signals
from .models.bigbird_encoder import get_bigbird_encoder
from .models.mini_lm_encoder import get_mini_lm_encoder
from .models.cross_encoder_model import get_cross_encoder
from .models.segment_llm_classifier import get_segment_llm_classifier
from .revalidation import apply_revalidation

_CHAPTER_START_RE = re.compile(r"^Chapter\s+\d+\s*$", re.I)
_CONTENTS_RE = re.compile(r"^CONTENTS\s*$", re.I)
_LEGAL_CITATION_RE = re.compile(
    r"\bv\.\s+[A-Z][a-z]|\bAIR\s+\d{4}\b|\bSCC\b|\bAll\s+ER\b|\bSC\b|\bHC\b"
    r"|\b\(\d{4}\)\s+\d+\s+[A-Z]+|\bILR\b|\bWLR\b"
)
_MINILM_THRESHOLD = 0.75
_MAX_LINE_GAP = 1
_MAX_PAGE_GAP = 2


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _build_reference_text(lines_text: List[str], label: str) -> str:
    """Format reference lines as annotated block for BigBird input."""
    tag = f"[{label.upper()}]"
    return "\n".join(f"{tag} {t}" for t in lines_text[:80] if t.strip())


def _format_segment_for_bigbird(
    segment_lines: List[Dict[str, Any]],
    signals_map: Dict[int, Dict[str, Any]],
) -> str:
    parts = []
    for line in segment_lines:
        lid = line.get("line_id")
        sig = signals_map.get(lid, {})
        ann = sig.get("annotation", "")
        text = (line.get("text") or "").strip()
        parts.append(f"{ann} {text}")
    return "\n".join(parts)


def _find_first_chapter_line_id(doubted_lines: List[Dict[str, Any]]) -> Optional[int]:
    """First 'Chapter N' line marks where integrated chapter body begins."""
    for line in doubted_lines:
        text = (line.get("text") or "").strip()
        if _CHAPTER_START_RE.match(text):
            lid = line.get("line_id")
            if lid is not None:
                return int(lid)
    return None


def _is_structural_boundary(text: str) -> bool:
    t = (text or "").strip()
    return bool(_CHAPTER_START_RE.match(t) or _CONTENTS_RE.match(t))


def _segment_has_legal_citation(lines: List[Dict[str, Any]]) -> bool:
    for line in lines:
        if _LEGAL_CITATION_RE.search((line.get("text") or "")):
            return True
    return False


def _looks_like_syllabus_block(
    heading_text: str,
    body_lines: List[Dict[str, Any]],
    *,
    first_toc_page: int,
) -> bool:
    """Duplicate chapter opener at the detected first-TOC page (no case citations)."""
    if first_toc_page <= 0:
        return False
    pages = [int(l.get("page_number") or 0) for l in body_lines]
    if not pages or min(pages) < first_toc_page:
        return False
    if _segment_has_legal_citation(body_lines):
        return False
    combined = f"{heading_text} " + " ".join(
        (l.get("text") or "").strip() for l in body_lines
    )
    if re.search(r"questions\s+(?:for|of)\s+this\s+chapter", combined, re.I):
        return True
    if re.search(r"the\s+following\s+\d+\s+topics?\s+are\s+discussed", combined, re.I):
        return True
    if _CHAPTER_START_RE.match((heading_text or "").strip()) and len(body_lines) <= 8:
        return True
    return False


def _group_into_segments(
    doubted_lines: List[Dict[str, Any]],
    heading_line_ids: Set[int],
    toc_seed_line_ids: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Group doubted lines into segments bounded by headings and structural breaks.

    Also splits when line_ids are non-contiguous (scattered TOC seeds) or pages
    jump sharply, so one heading does not absorb distant numbered-list lines.
    """
    toc_seeds = toc_seed_line_ids or set()
    segments: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    def _flush() -> None:
        nonlocal current
        if current is not None:
            segments.append(current)
            current = None

    for line in doubted_lines:
        lid = line.get("line_id")
        if lid is None:
            continue
        lid = int(lid)
        text = (line.get("text") or "").strip()
        is_heading = lid in heading_line_ids
        is_boundary = _is_structural_boundary(text)
        is_toc_seed = lid in toc_seeds

        if current is not None:
            prev = current["all_lines"][-1]
            prev_lid = int(prev.get("line_id") or 0)
            prev_page = int(prev.get("page_number") or 0)
            cur_page = int(line.get("page_number") or 0)
            if lid - prev_lid > _MAX_LINE_GAP or abs(cur_page - prev_page) > _MAX_PAGE_GAP:
                _flush()

        if is_toc_seed:
            _flush()
            segments.append({
                "heading_line_id": lid,
                "heading_text": text,
                "body_lines": [],
                "all_lines": [line],
            })
            continue

        if is_heading or is_boundary or current is None:
            _flush()
            current = {
                "heading_line_id": lid if (is_heading or is_boundary) else None,
                "heading_text": text if (is_heading or is_boundary) else "",
                "body_lines": [] if (is_heading or is_boundary) else [line],
                "all_lines": [line],
            }
        else:
            current["body_lines"].append(line)
            current["all_lines"].append(line)

    _flush()
    return segments


def resolve_doubted_section(
    doubted_line_ids: List[int],
    all_lines: List[Dict[str, Any]],
    confirmed_heading_line_ids: Set[int],
    confirmed_heading_texts: Set[str],
    confirmed_content_line_ids: Set[int],
    confirmed_toc_line_ids: Set[int],
    *,
    first_toc_page: int = 0,
    first_toc_section_start_line_id: Optional[int] = None,
    doubted_toc_line_ids: Optional[Set[int]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Main entry point.

    Parameters:
        doubted_line_ids        : IDs of lines in the doubted section
        all_lines               : All layout lines (list of dicts with line_id, text, page_number, etc.)
        confirmed_heading_line_ids : Heading line IDs within the doubted section
        confirmed_heading_texts : Text of confirmed headings from non-doubted pages (MiniLM reference)
        confirmed_content_line_ids : Line IDs from confirmed fragment body (after TOC page)
        confirmed_toc_line_ids  : Line IDs from confirmed TOC spans
        first_toc_page          : Page where the first TOC section was detected
        first_toc_section_start_line_id : First line of that TOC span (prefix ends before this)
        doubted_toc_line_ids    : Scattered TOC seed line IDs flagged in stage 14

    Returns:
        (segment results, revalidation audit log)
    """
    line_by_id: Dict[int, Dict] = {
        l.get("line_id"): l for l in all_lines if l.get("line_id") is not None
    }

    # Preserve document order
    ordered_ids = sorted(int(x) for x in doubted_line_ids)
    doubted_lines = [line_by_id[lid] for lid in ordered_ids if lid in line_by_id]

    toc_seed_ids: Set[int] = set(doubted_toc_line_ids or ())

    signals_map: Dict[int, Dict[str, Any]] = {}
    for line in doubted_lines:
        lid = line.get("line_id")
        text = (line.get("text") or "").strip()
        signals_map[lid] = compute_line_signals(
            text=text,
            page_number=int(line.get("page_number") or 0),
            is_bold=bool(line.get("is_bold", False)),
            word_count_hint=None,
            confirmed_heading_texts=confirmed_heading_texts,
        )

    first_body_line_id = _find_first_chapter_line_id(doubted_lines)
    segments = _group_into_segments(
        doubted_lines, confirmed_heading_line_ids, toc_seed_ids
    )

    from src import config

    llm_classifier = get_segment_llm_classifier()
    resolver_mode = (config.DOUBTED_RESOLVER_MODE or "revalidate_selected").strip().lower()
    use_bigbird = (config.DOUBTED_RESOLVER_LLM or "off").strip().lower() == "bigbird"
    use_inline_llm = llm_classifier.enabled and resolver_mode != "revalidate_selected"

    mini_lm = get_mini_lm_encoder()
    cross_enc = get_cross_encoder()

    ref_content_bb = None
    ref_toc_bb = None
    ref_metadata_bb = None
    bigbird = None
    if use_bigbird:
        bigbird = get_bigbird_encoder()
        ref_content_texts = [
            (line_by_id[lid].get("text") or "").strip()
            for lid in list(confirmed_content_line_ids)[:80]
            if lid in line_by_id
        ]
        ref_toc_texts = [
            (line_by_id[lid].get("text") or "").strip()
            for lid in list(confirmed_toc_line_ids)[:40]
            if lid in line_by_id
        ]
        ref_content_bb = bigbird.encode(_build_reference_text(ref_content_texts, "real_content"))
        ref_toc_bb = bigbird.encode(_build_reference_text(ref_toc_texts, "toc"))
        ref_metadata_text = (
            "[METADATA] ISBN 978-93-5107-000-0\n"
            "[METADATA] © 2018 Publisher\n"
            "[METADATA] All rights reserved. No part of this publication...\n"
            "[METADATA] Published by: Legal Publishers\n"
            "[METADATA] THE PUBLISHERS\n"
            "[METADATA] BOOKS RECOMMENDED FOR FURTHER READING\n"
        )
        ref_metadata_bb = bigbird.encode(ref_metadata_text)

    confirmed_heading_list = sorted(confirmed_heading_texts)
    conf_h_embs = mini_lm.encode(confirmed_heading_list) if confirmed_heading_list else None

    results: List[Dict[str, Any]] = []

    for seg_idx, seg in enumerate(segments):
        all_seg_lines = seg["all_lines"]
        heading_text = seg["heading_text"]
        body_lines = seg["body_lines"]
        body_text = " ".join((l.get("text") or "").strip() for l in body_lines)[:400]

        seg_line_ids = [int(l.get("line_id")) for l in all_seg_lines if l.get("line_id") is not None]
        seg_min = min(seg_line_ids) if seg_line_ids else 0
        seg_max = max(seg_line_ids) if seg_line_ids else 0
        seg_page = int(all_seg_lines[0].get("page_number") or 0) if all_seg_lines else 0
        seg_page_end = int(all_seg_lines[-1].get("page_number") or 0) if all_seg_lines else 0

        seg_meta = sum(signals_map.get(l.get("line_id"), {}).get("metadata_score", 0) for l in all_seg_lines)
        seg_toc = sum(signals_map.get(l.get("line_id"), {}).get("toc_score", 0) for l in all_seg_lines)
        seg_body = sum(signals_map.get(l.get("line_id"), {}).get("content_score", 0) for l in all_seg_lines)
        n_lines = max(len(all_seg_lines), 1)

        seg_meta_avg = seg_meta / n_lines
        seg_toc_avg = seg_toc / n_lines
        seg_body_avg = seg_body / n_lines

        base_result = {
            "segment_id": f"DS_{seg_idx:04d}",
            "heading_text": heading_text,
            "heading_line_id": seg["heading_line_id"],
            "page_start": seg_page,
            "page_end": seg_page_end,
            "line_count": n_lines,
            "body_line_count": len(body_lines),
            "signal_scores": {
                "metadata_avg": round(seg_meta_avg, 2),
                "toc_avg": round(seg_toc_avg, 2),
                "content_avg": round(seg_body_avg, 2),
            },
            "line_ids": seg_line_ids,
        }

        # ── 0a: Scattered TOC seed lines (non-contiguous numbered entries) ───
        if toc_seed_ids and seg_line_ids and set(seg_line_ids).issubset(toc_seed_ids):
            results.append({
                **base_result,
                "resolved_as": "toc",
                "method": "doubted_toc_seed",
                "confidence": 0.9,
            })
            continue

        # ── 0b: Entire segment is before first Chapter N → metadata ──────────
        if first_body_line_id is not None and seg_max < first_body_line_id:
            results.append({
                **base_result,
                "resolved_as": "metadata",
                "method": "before_first_chapter",
                "confidence": 0.95,
            })
            continue

        # ── 0c: Syllabus only BEFORE first Chapter N (not integrated openers) ─
        if (
            first_body_line_id is not None
            and seg_max < first_body_line_id
            and _looks_like_syllabus_block(heading_text, all_seg_lines, first_toc_page=first_toc_page)
        ):
            results.append({
                **base_result,
                "resolved_as": "toc",
                "method": "syllabus_at_first_toc_page",
                "confidence": 0.85,
            })
            continue

        # ── 0d: Segment starts at/after first TOC section line → prefer toc ─
        if (
            first_toc_section_start_line_id is not None
            and seg_min >= first_toc_section_start_line_id
            and seg_toc_avg >= seg_body_avg
        ):
            results.append({
                **base_result,
                "resolved_as": "toc",
                "method": "first_toc_section_span",
                "confidence": round(min(1.0, seg_toc_avg / 4.0), 3),
            })
            continue

        scores = {"metadata": seg_meta_avg, "toc": seg_toc_avg, "real_content": seg_body_avg}
        top_cat = max(scores, key=scores.get)
        top_score = scores[top_cat]
        second_score = sorted(scores.values())[-2]

        if top_score >= 1.0 and (top_score - second_score) >= 1.5:
            results.append({
                **base_result,
                "resolved_as": top_cat,
                "method": "deterministic",
                "confidence": round(min(1.0, top_score / 5.0), 3),
            })
            continue

        bb_sims: Dict[str, float] = {}

        if use_bigbird and bigbird is not None:
            seg_formatted = _format_segment_for_bigbird(all_seg_lines, signals_map)
            seg_bb = bigbird.encode(seg_formatted)
            if seg_bb is not None and ref_content_bb is not None:
                bb_sims["real_content"] = _cosine(seg_bb, ref_content_bb)
            if seg_bb is not None and ref_toc_bb is not None:
                bb_sims["toc"] = _cosine(seg_bb, ref_toc_bb)
            if seg_bb is not None and ref_metadata_bb is not None:
                bb_sims["metadata"] = _cosine(seg_bb, ref_metadata_bb)
            if bb_sims:
                bb_top = max(bb_sims, key=bb_sims.get)
                bb_top_score = bb_sims[bb_top]
                bb_sorted = sorted(bb_sims.values(), reverse=True)
                bb_gap = bb_sorted[0] - bb_sorted[1] if len(bb_sorted) >= 2 else 0.0
                if bb_top_score >= 0.68 and bb_gap >= 0.10:
                    results.append({
                        **base_result,
                        "resolved_as": bb_top,
                        "method": "bigbird",
                        "confidence": round(bb_top_score, 3),
                        "bigbird_sims": {k: round(v, 3) for k, v in bb_sims.items()},
                        "bigbird_gap": round(bb_gap, 4),
                    })
                    continue

        # MiniLM only for chapter-body segments (at/after first Chapter N)
        in_chapter_body = (
            first_body_line_id is None
            or seg_min >= first_body_line_id
        )
        if heading_text and conf_h_embs is not None and in_chapter_body:
            h_embs = mini_lm.encode([heading_text])
            if h_embs is not None:
                max_sim = mini_lm.max_similarity(h_embs[0], conf_h_embs)
                if max_sim >= _MINILM_THRESHOLD:
                    results.append({
                        **base_result,
                        "resolved_as": "real_content",
                        "method": "miniLM_heading_sim",
                        "confidence": round(float(max_sim), 3),
                    })
                    continue

        if heading_text and body_text and in_chapter_body:
            ms_score = cross_enc.score_one(heading_text, body_text[:300])
            if ms_score >= 0.50:
                results.append({
                    **base_result,
                    "resolved_as": "real_content",
                    "method": "msmarco",
                    "confidence": round(ms_score, 3),
                })
                continue

        if use_inline_llm:
            llm_result = llm_classifier.classify(
                heading_text,
                all_seg_lines,
                page_start=seg_page,
                page_end=seg_page_end,
            )
            if llm_result is not None:
                llm_cat, llm_conf = llm_result
                results.append({
                    **base_result,
                    "resolved_as": llm_cat,
                    "method": f"llm_{llm_classifier.backend}",
                    "confidence": round(llm_conf, 3),
                })
                continue

        if first_body_line_id is not None and seg_max < first_body_line_id:
            fallback_cat = "metadata"
        elif first_body_line_id is not None and seg_min >= first_body_line_id:
            fallback_cat = "real_content"
        elif seg_page <= 3 and seg_meta_avg >= seg_body_avg:
            fallback_cat = "metadata"
        elif (
            first_body_line_id is not None
            and seg_max < first_body_line_id
            and _looks_like_syllabus_block(heading_text, all_seg_lines, first_toc_page=first_toc_page)
        ):
            fallback_cat = "toc"
        else:
            fallback_cat = "metadata"
        bb_conf = round(bb_sims.get(fallback_cat, 0.5), 3) if bb_sims else 0.5
        results.append({
            **base_result,
            "resolved_as": fallback_cat,
            "method": "page_position_fallback",
            "confidence": bb_conf,
            "bigbird_sims": {k: round(v, 3) for k, v in bb_sims.items()} if bb_sims else {},
        })

    audits: List[Dict[str, Any]] = []
    if resolver_mode == "revalidate_selected":
        neighbor_headings = sorted(confirmed_heading_texts)[:20]
        results, audits = apply_revalidation(
            results,
            line_by_id,
            neighbor_headings=neighbor_headings,
            confidence_threshold=float(config.DOUBTED_REVALIDATION_CONFIDENCE or 0.85),
            max_candidates=int(config.DOUBTED_REVALIDATION_MAX or 40),
            first_body_line_id=first_body_line_id,
        )

    return results, audits

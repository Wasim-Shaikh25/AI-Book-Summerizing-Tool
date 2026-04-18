"""
Phase 1 (restructure only):
This module is the production-facing pipeline entrypoint for the new clean deterministic core.

IMPORTANT:
- Imports from ONLY the new clean core modules.
- No imports from src/legacy.
- Logic is intentionally minimal/stubbed for now (behavior will be implemented in later phases).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

from src.ingestion.layout_enrichment import lines_to_log
from src.ingestion.pdf_extractor import extract_pdf
from src.ingestion.text_normalizer import normalize_text
from src.structure.candidate_scoring import collect_candidates_scored
from src.structure.fragments import build_fragments
from src.structure.noise_filter import mark_noise
from src.structure.toc_cleaning import clean_toc
from src.structure.toc_repeat_detection import (
    book_metadata_from_first_toc_section,
    build_toc_sections_from_repeated_headings,
    detect_deterministic_toc,
)
from src.structure.logging.pipeline_logger import PipelineLogger
from src.structure.pre_llm_gate import gate_heading_validity_candidates


def _final_headings_without_toc_and_metadata(
    final_headings_items: List[Dict[str, Any]],
    book_metadata_line_ids: Set[int],
) -> List[Dict[str, Any]]:
    """
    Drop headings that are TOC, in a TOC section, or in book metadata (prefix + first TOC block).
    Strips is_toc / in_toc_section from surviving rows.
    """
    out: List[Dict[str, Any]] = []
    for it in final_headings_items:
        if it.get("is_toc"):
            continue
        if it.get("in_toc_section"):
            continue
        lid = it.get("line_id")
        if isinstance(lid, int) and lid in book_metadata_line_ids:
            continue
        row = {k: v for k, v in it.items() if k not in ("is_toc", "in_toc_section")}
        out.append(row)
    return out


def _parse_line_id_from_heading_id(hid: Any) -> Optional[int]:
    if not isinstance(hid, str):
        return None
    if not hid.startswith("L"):
        return None
    try:
        return int(hid[1:].split(":", 1)[0])
    except Exception:
        return None


def run_pipeline(pdf_path: str, *, enable_logs: bool = False, persist_to_db: bool = False):
    """
    Orchestrates the clean core pipeline.

    Logging:
      - enable_logs=False (default): no log folder/files are created
      - enable_logs=True: writes exactly the 10 whitelisted stage logs under logs/run_<timestamp>/
    """
    logger = PipelineLogger.create(pdf_file=Path(pdf_path).name, enabled=enable_logs)

    pdf_doc = extract_pdf(pdf_path)
    lines = normalize_text(pdf_doc)

    # Stage 01: layout extraction
    layout_payload = lines_to_log(lines)
    logger.write_stage("layout_lines", layout_payload)
    layout_by_line_id = {it["line_id"]: it for it in layout_payload if isinstance(it, dict) and isinstance(it.get("line_id"), int)}

    # Stage 02: noise detection (never deletes lines)
    lines, noise_log = mark_noise(lines)
    logger.write_stage("noise_filter", noise_log)

    # Stage 03: candidate scoring (authoritative candidate selection)
    candidates, scoring_log = collect_candidates_scored(lines)
    logger.write_stage("candidate_scoring", scoring_log)

    # Layer 1: eliminate fake headings with deterministic pre-LLM rules.
    candidates, gate_log = gate_heading_validity_candidates(candidates, lines=lines)
    logger.write_stage("pre_llm_heading_gate", gate_log)

    # Layer 2: continuity validation without any LLM intermediate step.
    # This step computes deterministic signals and only keeps headings that remain plausible.
    from .models import FinalHeading

    def _continuity_signals(candidate: Any, line_obj: Any) -> list[str]:
        text = (getattr(candidate, "text", "") or "").strip()
        signals: list[str] = []
        if text:
            if text[0].isupper():
                signals.append("starts_uppercase")
            if len(text.split()) <= 12:
                signals.append("short_heading_like")
            if bool(getattr(line_obj, "is_bold", False)):
                signals.append("bold")
            if bool(getattr(line_obj, "large_font", False)):
                signals.append("large_font")
            if bool(getattr(line_obj, "centered", False)) or bool(getattr(line_obj, "is_centered", False)):
                signals.append("centered")
            if __import__("re").match(r"^(?:\d+(?:\.\d+)*|[IVXLCDM]+\.|[A-Z]\.|[a-z]\.)\s+", text, __import__("re").IGNORECASE):
                signals.append("numbered_section")
            if text.endswith(":"):
                signals.append("trailing_colon")
        return signals

    headings = []
    dropped_continuity_log = []
    for c in candidates:
        hid = getattr(c, "id", None) or getattr(c, "heading_id", None)
        lid = _parse_line_id_from_heading_id(hid) or getattr(c, "start_line", None) or 0
        line_obj = layout_by_line_id.get(lid)
        signals = _continuity_signals(c, line_obj)
        # deterministic drop for body-like text that survived layer 1
        text = (getattr(c, "text", "") or "").strip()
        word_count = len(text.split())
        body_like = (
            word_count >= 14
            or text.endswith(".")
            or "," in text
            or ";" in text
            or (word_count >= 8 and not signals)
        )

        if body_like and not any(sig in signals for sig in ("bold", "large_font", "centered", "numbered_section")):
            dropped_reason = "continuity_drop(body_like_no_heading_signals)"
            dropped_continuity_log.append(
                {
                    "heading_id": hid,
                    "text": text,
                    "action": "drop_by_continuity",
                    "reason": dropped_reason,
                    "signals_used": signals,
                    "line_id": lid,
                }
            )
            continue

        if text and not any(sig in signals for sig in ("bold", "large_font", "centered", "numbered_section")):
            low_signal_body = (
                len(text.split()) >= 10
                or text.endswith(".")
                or "," in text
                or ";" in text
                or ":" in text
                or re.search(r"\b(?:which|that|because|therefore|however|whereas|although|since|while|when|where|this|these|those|they|it)\b", text, re.IGNORECASE)
            )
            if low_signal_body:
                dropped_continuity_log.append(
                    {
                        "heading_id": hid,
                        "text": text,
                        "action": "drop_by_continuity",
                        "reason": "continuity_drop(sentence_like_body)",
                        "signals_used": signals,
                        "line_id": lid,
                    }
                )
                continue

        continuity_reason = "continuity_valid(" + ",".join(signals) + ")" if signals else "continuity_valid(no_strong_signals)"
        headings.append(
            FinalHeading(
                id=hid,
                text=getattr(c, "text", ""),
                line_id=int(lid) if isinstance(lid, int) else 0,
                fragment_id=None,
                parent_heading=None,
                reason=continuity_reason,
                signals_used=signals,
                confidence=getattr(c, "confidence", None),
            )
        )
    if dropped_continuity_log:
        logger.write_stage("continuity_filter", dropped_continuity_log)

    fragments_result, fragments_log = build_fragments(lines, headings)
    logger.write_stage("fragments", fragments_log)

    heading_to_fragment_id = getattr(fragments_result, "heading_to_fragment_id", {}) or {}
    for h in headings:
        hid = getattr(h, "id", None)
        if isinstance(hid, str) and hid in heading_to_fragment_id:
            h.fragment_id = heading_to_fragment_id[hid]

    final_heads = headings
    toc_out = clean_toc(final_heads, fragments=fragments_result.fragments)

    toc_seed_ids, det_seed_log = detect_deterministic_toc(lines, toc_out)
    for h in toc_out:
        lid = getattr(h, "line_id", None)
        h.is_toc = bool(isinstance(lid, int) and lid in toc_seed_ids)

    toc_section_line_ids, det_section_log = build_toc_sections_from_repeated_headings(lines, toc_out)
    for h in toc_out:
        lid = getattr(h, "line_id", None)
        h.in_toc_section = bool(isinstance(lid, int) and lid in toc_section_line_ids)

    det_toc_log_items = det_seed_log + det_section_log

    book_metadata_line_ids, book_meta_log = book_metadata_from_first_toc_section(lines, det_section_log)

    # Stage 08: final headings after continuity validation and cleanup.
    final_headings_items = []
    for h in toc_out:
        hid = getattr(h, "id", None)
        lid = _parse_line_id_from_heading_id(hid) if isinstance(hid, str) else None
        page_number = None
        if isinstance(lid, int):
            layout = layout_by_line_id.get(lid)
            if isinstance(layout, dict):
                page_number = layout.get("page_number")

        final_headings_items.append(
            {
                "heading_id": hid,
                "text": getattr(h, "text", ""),
                "level": getattr(h, "level", None),
                "parent_heading": getattr(h, "parent_heading", None),
                "fragment_id": getattr(h, "fragment_id", None),
                "page_number": page_number,
                "line_id": lid,
                "confidence": getattr(h, "confidence", None),
                "reason": getattr(h, "reason", None),
                "signals_used": getattr(h, "signals_used", None),
                "is_toc": bool(getattr(h, "is_toc", False)),
                "in_toc_section": bool(getattr(h, "in_toc_section", False)),
            }
        )
    logger.write_stage("final_headings", final_headings_items)
    logger.write_stage(
        "final_headings_2",
        _final_headings_without_toc_and_metadata(final_headings_items, book_metadata_line_ids),
    )
    logger.write_stage("deterministic_toc", det_toc_log_items)
    logger.write_stage("book_metadata", book_meta_log)

    # Return production artifacts (DB/export can be built from this)
    from .models import PipelineResult

    result = PipelineResult(
        final_headings=toc_out,
        fragments=getattr(fragments_result, "fragments", []) or [],
        heading_to_fragment_id=getattr(fragments_result, "heading_to_fragment_id", {}) or {},
    )

    # Production persistence (DB becomes source-of-truth)
    if persist_to_db:
        from src.storage.book_repository import BookRepository
        from src.storage.knowledge_store import KnowledgeStore
        from src.storage.schema import BookMetadata
        from src.storage.toc_repository import TocRepository

        store = KnowledgeStore()
        book_repo = BookRepository(store)
        repo = TocRepository(store)

        book = BookMetadata(
            title=Path(pdf_path).stem,
            subject="unknown",
            source_file_name=Path(pdf_path).name,
            total_pages=0,
        )
        book_repo.save_book(book)

        repo.save_full_toc(
            book_id=book.book_id,
            final_headings=result.final_headings,
            fragments=result.fragments,
            heading_to_fragment_id=result.heading_to_fragment_id,
            clear_existing=True,
        )

        if logger is not None:
            stage_files = {
                "layout_lines": "01_layout_lines.json",
                "noise_filter": "02_noise_filter.json",
                "candidate_scoring": "03_candidate_scoring.json",
                "pre_llm_heading_gate": "03b_pre_llm_heading_gate.json",
                "llm_heading_validation": "04_llm_heading_validation.json",
                "pre_llm_toc_gate": "04b_pre_llm_toc_gate.json",
                "llm_toc_classification": "05_llm_toc_classification.json",
                "toc_section_eval": "06_toc_section_eval.json",
                "fragments": "07_fragments.json",
                "hierarchy": "08_hierarchy.json",
                "continuity_filter": "08b_continuity_filter.json",
                "final_headings": "09_final_headings.json",
                "deterministic_toc": "10_deterministic_toc.json",
                "book_metadata": "11_book_metadata.json",
                "final_headings_2": "12_final_headings_2.json",
                "decision_trace": "decision_trace.json",
            }
            for stage_name, filename in stage_files.items():
                path = logger.run_dir / filename
                if not path.exists():
                    continue
                payload = path.read_text(encoding="utf-8")
                store.save_pipeline_artifact(
                    book_id=book.book_id,
                    stage_name=stage_name,
                    filename=filename,
                    payload=payload,
                    run_id=getattr(logger, "run_id", None),
                )

    return result, (logger if enable_logs else None)

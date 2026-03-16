from __future__ import annotations

from typing import Any, Dict, List, Optional

from .gemini_toc import gemini_toc
from .logging.pipeline_logger import PipelineLogger
from .models import HeadingCandidate


def classify_toc(
    headings: List[HeadingCandidate],
    *,
    logger: PipelineLogger,
) -> List[HeadingCandidate]:
    """
    Gemini TOC stage (batched).

    Refactor:
      - Writes exactly one per-run file: 05_gemini_toc_classification.json
      - No separate request/raw/results JSON logs
    """
    batches = gemini_toc(headings, batch_size=20)

    parsed_results_by_id: Dict[str, Dict[str, Any]] = {}
    req_batches: List[Dict[str, Any]] = []
    raw_batches: List[Dict[str, Any]] = []

    for batch_id, _batch_candidates, parsed_by_id, raw_text, request_items in batches:
        req_batches.append(
            {"batch_id": batch_id, "model": "gemini", "request": request_items}
        )
        raw_batches.append({"batch_id": batch_id, "raw_model_text": raw_text})
        for hid, v in parsed_by_id.items():
            parsed_results_by_id[hid] = v

    # Refactor: do not write separate request/raw files. Their info is merged into the stage log.

    out: List[HeadingCandidate] = []
    parsed_log: List[Dict[str, Any]] = []

    for h in headings:
        rec = parsed_results_by_id.get(h.id)
        if rec is None:
            out.append(h)
            continue
        is_toc = rec.get("is_toc")
        reason = rec.get("reason", "")
        if not isinstance(is_toc, bool):
            out.append(h)
            continue

        updated = HeadingCandidate(
            id=h.id,
            text=h.text,
            start_line=h.start_line,
            end_line=h.end_line,
            before_context=list(h.before_context),
            after_context=list(h.after_context),
            full_context_preview=h.full_context_preview,
            is_valid=h.is_valid,
            valid_reason=h.valid_reason,
            is_toc=is_toc,
            toc_reason=reason if isinstance(reason, str) else "",
        )
        out.append(updated)

        parsed_log.append(
            {
                "heading_id": updated.id,
                "text": updated.text,
                "is_toc": updated.is_toc,
                "reason": updated.toc_reason,
            }
        )

        logger.record_decision(
            updated.id,
            stage="gemini_toc",
            decision="is_toc_true" if updated.is_toc else "is_toc_false",
            metadata={"reason": updated.toc_reason or ""},
        )

    logger.write_stage("gemini_toc_classification", parsed_log)

    return out

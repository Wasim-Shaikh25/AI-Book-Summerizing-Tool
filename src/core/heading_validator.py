from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .gemini_validity import gemini_validate
from .logging.pipeline_logger import PipelineLogger
from .models import HeadingCandidate


# Prompt logic for Gemini validity is owned by src/core/gemini_validity.py


def _ensure_logs_dir() -> Path:
    # Legacy: keep for older callers (writes flat logs under ./logs)
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _candidate_to_log_dict(c: HeadingCandidate) -> Dict:
    # Human-readable, stable ordering
    return {
        "id": c.id,
        "text": c.text,
        "start_line": c.start_line,
        "end_line": c.end_line,
        "before_context": c.before_context,
        "after_context": c.after_context,
        "full_context_preview": c.full_context_preview,
        "is_valid": c.is_valid,
    }


def _build_request_payload(candidates: Sequence[HeadingCandidate]) -> Dict:
    # Legacy payload builder kept to avoid breaking existing code paths.
    return {
        "candidates": [
            {
                "id": c.id,
                "text": c.text,
                "full_context_preview": c.full_context_preview,
            }
            for c in candidates
        ]
    }


def validate_headings(
    candidates: List[HeadingCandidate],
    *,
    logger: Optional[PipelineLogger] = None,
) -> List[HeadingCandidate]:
    """
    Gemini heading validation stage (batched).

    If `logger` is provided, writes per-run files (per requirements):
      - 05_gemini_request.json (list of batches)
      - 05_gemini_raw_response.json (list of batches)
      - 05_gemini_heading_validation.json (parsed per heading; no raw text)

    If `logger` is not provided, preserves the legacy flat log behavior under ./logs.
    """
    # Legacy flat logs (for backwards compatibility)
    if logger is None:
        logs_dir = _ensure_logs_dir()
        raw_payload = [_candidate_to_log_dict(c) for c in candidates]
        _write_json(logs_dir / "heading_candidates_raw.json", raw_payload)

        request_payload = _build_request_payload(candidates)
        _write_json(logs_dir / "heading_validation_request.json", request_payload)

        # Legacy returns candidates unchanged (safe default) if no logger provided.
        # (The new pipeline always passes logger.)
        return candidates

    # Batched Gemini call
    batches = gemini_validate(candidates, batch_size=20)

    # Accumulate parsed results across batches
    parsed_results_by_id: Dict[str, Dict[str, Any]] = {}
    request_batches_payload: List[Dict[str, Any]] = []
    raw_batches_payload: List[Dict[str, Any]] = []

    for batch_id, batch_candidates, parsed_by_id, raw_text, request_items in batches:
        request_batches_payload.append(
            {
                "batch_id": batch_id,
                "model": "gemini",
                "request": request_items,
            }
        )
        raw_batches_payload.append(
            {
                "batch_id": batch_id,
                "raw_model_text": raw_text,
            }
        )
        for hid, v in parsed_by_id.items():
            parsed_results_by_id[hid] = v

    # Requirement: append per batch (do not overwrite). Each file is a JSON list of batches.
    for entry in request_batches_payload:
        logger.append_json_list("05_gemini_request.json", entry)
    for entry in raw_batches_payload:
        logger.append_json_list("05_gemini_raw_response.json", entry)

    validated: List[HeadingCandidate] = []
    parsed_log: List[Dict[str, Any]] = []

    for c in candidates:
        rec = parsed_results_by_id.get(c.id)
        if rec is None:
            validated.append(c)
            continue

        is_valid = rec.get("is_valid")
        reason = rec.get("reason", "")
        if not isinstance(is_valid, bool):
            validated.append(c)
            continue

        updated = HeadingCandidate(
            id=c.id,
            text=c.text,
            start_line=c.start_line,
            end_line=c.end_line,
            before_context=list(c.before_context),
            after_context=list(c.after_context),
            full_context_preview=c.full_context_preview,
            is_valid=is_valid,
            valid_reason=reason if isinstance(reason, str) else "",
        )
        validated.append(updated)
        parsed_log.append(
            {
                "heading_id": updated.id,
                "text": updated.text,
                "is_valid": updated.is_valid,
                "is_toc": updated.is_toc if updated.is_toc is not None else False,
                "reason": updated.valid_reason,
            }
        )

        logger.append_decision(
            updated.id,
            stage="gemini_heading_validation",
            decision="is_valid_true" if updated.is_valid else "is_valid_false",
            meta={"reason": updated.valid_reason},
        )

    logger.write_json("05_gemini_heading_validation.json", parsed_log)

    return validated

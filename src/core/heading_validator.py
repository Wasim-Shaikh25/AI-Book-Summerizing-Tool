from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Sequence

from src.ai.gemini_adapter import gemini_generate
from .models import HeadingCandidate


SYSTEM_INSTRUCTION = (
    "You are validating structural headings in academic PDFs. "
    "You will be given a list of detected heading candidates with context. "
    "Return ONLY a JSON array of objects with fields: "
    "[{ \"id\": \"...\", \"is_valid\": true/false }]. "
    "No explanations, no extra keys, no markdown."
)


def _ensure_logs_dir() -> Path:
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
    return {
        "system_instruction": SYSTEM_INSTRUCTION,
        "candidates": [
            {
                "id": c.id,
                "text": c.text,
                "full_context_preview": c.full_context_preview,
            }
            for c in candidates
        ],
        "response_format": '[{ "id": "...", "is_valid": true/false }]',
        "rules": {
            "return_only_json": True,
            "no_explanations": True,
            "no_markdown": True,
            "no_extra_keys": True,
        },
    }


def validate_headings(candidates: List[HeadingCandidate]) -> List[HeadingCandidate]:
    """
    Accepts List[HeadingCandidate], sends a JSON validation request to Gemini,
    receives structured response, updates is_valid, and writes logs.

    Logs written under ./logs (created if missing):
      - heading_candidates_raw.json
      - heading_validation_request.json
      - heading_validation_response.json
      - heading_candidates_filtered.json
    """
    logs_dir = _ensure_logs_dir()

    # Log raw candidates as detected
    raw_payload = [_candidate_to_log_dict(c) for c in candidates]
    _write_json(logs_dir / "heading_candidates_raw.json", raw_payload)

    # Build request
    request_payload = _build_request_payload(candidates)
    _write_json(logs_dir / "heading_validation_request.json", request_payload)

    # User prompt: provide ONLY the candidates JSON to the model (system instruction enforces format)
    user_prompt = json.dumps(request_payload["candidates"], indent=2, ensure_ascii=False)

    # Send to Gemini (no batching)
    resp = gemini_generate(SYSTEM_INSTRUCTION, user_prompt)

    # Log response (raw + parsed if possible)
    response_payload = {
        "raw_text": resp.raw_text,
        "parsed_json": resp.parsed_json,
    }
    _write_json(logs_dir / "heading_validation_response.json", response_payload)

    # Apply validation results
    id_to_is_valid: Dict[str, bool] = {}
    if isinstance(resp.parsed_json, list):
        for item in resp.parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id")
            is_valid = item.get("is_valid")
            if isinstance(hid, str) and isinstance(is_valid, bool):
                id_to_is_valid[hid] = is_valid

    validated: List[HeadingCandidate] = []
    for c in candidates:
        if c.id in id_to_is_valid:
            validated.append(
                HeadingCandidate(
                    id=c.id,
                    text=c.text,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    before_context=list(c.before_context),
                    after_context=list(c.after_context),
                    full_context_preview=c.full_context_preview,
                    is_valid=id_to_is_valid[c.id],
                )
            )
        else:
            # If Gemini didn't return an entry, leave as None (safe default)
            validated.append(c)

    # Filtered list: only those marked valid==True
    filtered = [c for c in validated if c.is_valid is True]
    filtered_payload = [_candidate_to_log_dict(c) for c in filtered]
    _write_json(logs_dir / "heading_candidates_filtered.json", filtered_payload)

    return validated

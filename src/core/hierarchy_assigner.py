from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence

from src.ai.gemini_adapter import gemini_generate
from src.core.logging.pipeline_logger import PipelineLogger
from .models import FinalHeading


SYSTEM_INSTRUCTION = (
    "You are assigning hierarchy levels to structural headings in academic PDFs. "
    "You will be given a JSON array of headings with fields: id, text, fragment_id. "
    "Return ONLY a JSON array of objects with fields: "
    "[{ \"id\": \"...\", \"level\": 1 }]. "
    "No explanations, no extra keys, no markdown."
)


def _ensure_logs_dir() -> Path:
    """
    Backward-compatible fallback for callers that don't pass a PipelineLogger.
    Prefer logging into the per-run folder via PipelineLogger.
    """
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def assign_hierarchy(headings: Sequence[FinalHeading], *, logger: PipelineLogger | None = None) -> List[FinalHeading]:
    """
    Input:
      List[FinalHeading]

    Sends to Gemini:
      [
        { "id": "...", "text": "...", "fragment_id": "..." }
      ]

    Gemini returns:
      [
        { "id": "...", "level": 1 }
      ]

    Updates FinalHeading.level.

    Logs:
      - logs/hierarchy_request.json
      - logs/hierarchy_response.json
    """
    logs_dir = logger.run_dir if logger is not None else _ensure_logs_dir()

    request_list = [
        {"id": h.id, "text": h.text, "fragment_id": h.fragment_id} for h in headings
    ]
    _write_json(logs_dir / "08_hierarchy_request.json", request_list)

    user_prompt = json.dumps(request_list, indent=2, ensure_ascii=False)
    resp = gemini_generate(SYSTEM_INSTRUCTION, user_prompt)

    response_payload = {"raw_text": resp.raw_text, "parsed_json": resp.parsed_json}
    _write_json(logs_dir / "08_hierarchy_response.json", response_payload)

    id_to_level: Dict[str, int] = {}
    if isinstance(resp.parsed_json, list):
        for item in resp.parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id")
            lvl = item.get("level")
            if isinstance(hid, str) and isinstance(lvl, int):
                id_to_level[hid] = lvl

    updated: List[FinalHeading] = []
    for h in headings:
        level = id_to_level.get(h.id, h.level)
        updated.append(
            FinalHeading(
                id=h.id,
                text=h.text,
                level=level,
                fragment_id=h.fragment_id,
            )
        )

    return updated

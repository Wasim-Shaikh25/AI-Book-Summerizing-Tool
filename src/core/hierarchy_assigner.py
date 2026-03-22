from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence

from src.core.logging.pipeline_logger import PipelineLogger
from src.LLMAdaptor.client import LLMClient

from .models import FinalHeading


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

    Logging contract:
      - Do NOT write any request/response JSON files.
      - Any hierarchy debugging must be captured via the centralized PipelineLogger stage logs.
    """
    request_list = [{"id": h.id, "text": h.text, "fragment_id": h.fragment_id} for h in headings]

    user_prompt = json.dumps(request_list, indent=2, ensure_ascii=False)
    resp = LLMClient.from_config().generate(
        "hierarchy",
        variables={"items_json": user_prompt},
        temperature=0.2,
        response_mime_type="application/json",
    )

    resp_model = getattr(resp, "model", None)
    resp_latency_ms = getattr(resp, "latency_ms", None)

    id_to_level: Dict[str, int] = {}
    id_to_parent: Dict[str, str | None] = {}
    id_to_reason: Dict[str, str | None] = {}
    id_to_signals: Dict[str, list[str] | None] = {}
    id_to_conf: Dict[str, float | None] = {}

    parsed_json = None
    try:
        parsed_json = json.loads(resp.text)
    except Exception:
        parsed_json = None

    if isinstance(parsed_json, list):
        for item in parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id")
            lvl = item.get("level")
            if isinstance(hid, str) and isinstance(lvl, int):
                id_to_level[hid] = lvl

                parent = item.get("parent_heading")
                if parent is None or isinstance(parent, str):
                    id_to_parent[hid] = parent

                reason = item.get("reason")
                if reason is None or isinstance(reason, str):
                    id_to_reason[hid] = reason

                signals = item.get("signals_used")
                if signals is None or isinstance(signals, list):
                    # Filter to strings only, keep order
                    if isinstance(signals, list):
                        signals = [s for s in signals if isinstance(s, str)]
                    id_to_signals[hid] = signals

                conf = item.get("confidence")
                if conf is None or isinstance(conf, (int, float)):
                    id_to_conf[hid] = float(conf) if isinstance(conf, (int, float)) else None

    updated: List[FinalHeading] = []
    for h in headings:
        hid = h.id
        level = id_to_level.get(hid, h.level)
        updated.append(
            FinalHeading(
                id=h.id,
                text=h.text,
                level=level,
                fragment_id=h.fragment_id,
                parent_heading=id_to_parent.get(hid),
                reason=id_to_reason.get(hid),
                signals_used=id_to_signals.get(hid),
                confidence=id_to_conf.get(hid),
                # Persisted/logged meta (not necessarily model output)
                hierarchy_model=resp_model,
                hierarchy_latency_ms=resp_latency_ms,
            )
        )

    return updated

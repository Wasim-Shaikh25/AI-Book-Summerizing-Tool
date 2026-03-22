from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Sequence, Tuple

from src.LLMAdaptor.client import LLMClient

from .models import HeadingCandidate


def _chunks(seq: Sequence[HeadingCandidate], n: int) -> List[List[HeadingCandidate]]:
    out: List[List[HeadingCandidate]] = []
    cur: List[HeadingCandidate] = []
    for x in seq:
        cur.append(x)
        if len(cur) >= n:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def build_validity_request_items(batch: Sequence[HeadingCandidate]) -> List[Dict[str, Any]]:
    return [
        {
            "heading_id": c.id,
            "text": c.text,
            "context_preview": c.full_context_preview,
        }
        for c in batch
    ]


def llm_validate_batch(
    batch: Sequence[HeadingCandidate],
) -> Tuple[Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]:
    """
    Returns:
      - parsed_by_heading_id: { heading_id: {"is_valid": bool, "reason": str} }
      - raw_model_text: exact model text (as returned by adapter)
      - request_items: list sent to Gemini (for logging)
    """
    request_items = build_validity_request_items(batch)

    user_prompt = json.dumps(
        request_items,
        ensure_ascii=False,
    )

    client = LLMClient.from_config()
    result = client.generate(
        "heading_validity",
        variables={"candidates_json": user_prompt},
        temperature=0.2,
        response_mime_type="application/json",
    )

    raw_text = result.text
    parsed: Dict[str, Dict[str, Any]] = {}

    # Accept either:
    #  1) [{"id":..., "is_valid":..., "reason":...}, ...]
    #  2) {"results":[{"id":...}, ...]}
    try:
        obj = json.loads(raw_text)
    except Exception:
        obj = None

    items = None
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict) and isinstance(obj.get("results"), list):
        items = obj["results"]

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            hid = item.get("id") or item.get("heading_id")
            is_valid = item.get("is_valid")
            reason = item.get("reason")
            if isinstance(hid, str) and isinstance(is_valid, bool):
                parsed[hid] = {"is_valid": is_valid, "reason": reason if isinstance(reason, str) else ""}

    return parsed, raw_text, request_items


def llm_validate(
    candidates: Sequence[HeadingCandidate],
    *,
    batch_size: int = 20,
) -> List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]]:
    """
    Returns a list of batches:
      (batch_id, batch_candidates, parsed_by_id, raw_model_text, request_items)
    """
    # Allow runtime override for tuning CPU-only Ollama:
    #   LLM_VALIDITY_BATCH_SIZE=10
    # This is intentionally generic (applies to any provider) but is most useful for local models.
    env_bs = os.getenv("LLM_VALIDITY_BATCH_SIZE")
    if env_bs:
        try:
            batch_size = max(1, int(env_bs))
        except Exception:
            pass

    batches = _chunks(candidates, batch_size)
    out: List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]] = []
    for i, b in enumerate(batches, start=1):
        parsed, raw_text, request_items = llm_validate_batch(b)
        out.append((i, b, parsed, raw_text, request_items))
    return out

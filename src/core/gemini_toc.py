from __future__ import annotations

import json
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


def build_toc_request_items(batch: Sequence[HeadingCandidate]) -> List[Dict[str, Any]]:
    return [
        {
            "heading_id": c.id,
            "text": c.text,
            "context_preview": c.full_context_preview,
        }
        for c in batch
    ]


def gemini_toc_batch(
    batch: Sequence[HeadingCandidate],
) -> Tuple[Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]:
    request_items = build_toc_request_items(batch)
    user_prompt = json.dumps(request_items, ensure_ascii=False)
    prompt = LLMClient.from_config().prompts.get("toc_classifier")
    resp = LLMClient.from_config().generate(
        system=prompt.system,
        user=user_prompt,
        temperature=0.2,
        response_mime_type="application/json",
    )

    parsed: Dict[str, Dict[str, Any]] = {}
    parsed_json = None
    try:
        parsed_json = json.loads(resp.text)
    except Exception:
        parsed_json = None

    if isinstance(parsed_json, list):
        for item in parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id") or item.get("heading_id")
            is_toc = item.get("is_toc")
            reason = item.get("reason")
            if isinstance(hid, str) and isinstance(is_toc, bool):
                parsed[hid] = {"is_toc": is_toc, "reason": reason if isinstance(reason, str) else ""}
    return parsed, resp.text, request_items


def gemini_toc(
    candidates: Sequence[HeadingCandidate],
    *,
    batch_size: int = 20,
) -> List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]]:
    batches = _chunks(candidates, batch_size)
    out: List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]] = []
    for i, b in enumerate(batches, start=1):
        parsed, raw_text, request_items = gemini_toc_batch(b)
        out.append((i, b, parsed, raw_text, request_items))
    return out

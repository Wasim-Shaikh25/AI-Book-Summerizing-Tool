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


def _try_parse_json_array(text: str):
    """
    Best-effort JSON array parser.
    Handles common LLM wrappers like ```json ... ``` and extra prose.
    Returns a Python object (usually list/dict) or None.
    """
    if not isinstance(text, str):
        return None

    s = text.strip()

    # Strip markdown fences
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
            s = "\n".join(lines[1:-1]).strip()

    # Direct parse
    try:
        return json.loads(s)
    except Exception:
        pass

    # Try extracting the first JSON array substring
    l = s.find("[")
    r = s.rfind("]")
    if l != -1 and r != -1 and r > l:
        try:
            return json.loads(s[l : r + 1])
        except Exception:
            pass

    # Try extracting the first JSON object substring (some models return {"items":[...]})
    l = s.find("{")
    r = s.rfind("}")
    if l != -1 and r != -1 and r > l:
        try:
            return json.loads(s[l : r + 1])
        except Exception:
            pass

    return None


def llm_toc_batch(
    batch: Sequence[HeadingCandidate],
) -> Tuple[Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]:
    request_items = build_toc_request_items(batch)
    user_prompt = json.dumps(request_items, ensure_ascii=False)

    resp = LLMClient.from_config().generate(
        "toc_classifier",
        variables={"items_json": user_prompt},
        temperature=0.2,
        response_mime_type="application/json",
    )

    parsed: Dict[str, Dict[str, Any]] = {}

    parsed_json = _try_parse_json_array(resp.text)

    # Allow {"items": [...]} wrapper
    if isinstance(parsed_json, dict) and isinstance(parsed_json.get("items"), list):
        parsed_json = parsed_json.get("items")

    if isinstance(parsed_json, list):
        for item in parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id") or item.get("heading_id")
            is_toc = item.get("is_toc")
            reason = item.get("reason")
            if isinstance(hid, str) and isinstance(is_toc, bool):
                parsed[hid] = {
                    "is_toc": is_toc,
                    "reason": reason if isinstance(reason, str) else "",
                }

    return parsed, resp.text, request_items


def llm_toc(
    candidates: Sequence[HeadingCandidate],
    *,
    batch_size: int = 20,
) -> List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]]:
    batches = _chunks(candidates, batch_size)
    out: List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]] = []
    for i, b in enumerate(batches, start=1):
        parsed, raw_text, request_items = llm_toc_batch(b)
        out.append((i, b, parsed, raw_text, request_items))
    return out

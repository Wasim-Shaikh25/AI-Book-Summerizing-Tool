from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from src.ai.gemini_adapter import gemini_generate
from .models import HeadingCandidate


SYSTEM_INSTRUCTION_VALID = (
    "You are validating structural headings in academic PDFs.\n"
    "You will be given a list of heading candidates with context previews.\n"
    "For each item, decide if it is a real structural heading in the MAIN BODY.\n"
    "\n"
    "Important rules:\n"
    "- DO NOT mark in-paragraph list/bullet items as headings.\n"
    "  Examples that are usually NOT headings:\n"
    "    * \"3. Deterrence: Deterrence theory about law says ...\"\n"
    "    * \"2. Safeguarding Interests: Another primary objective ...\"\n"
    "    * \"a. Distinction between ...\" (lettered list items)\n"
    "- Section/chapter numbering like \"1.2 Something\" or \"3.1 Something\" CAN be a real heading.\n"
    "- If the line starts with a single number + dot (e.g., \"3.\"), and then continues as a long sentence,\n"
    "  treat it as body-list content, not a structural heading.\n"
    "\n"
    "Return ONLY a JSON array of objects:\n"
    "[{ \"id\": \"...\", \"is_valid\": true/false, \"reason\": \"...\" }]\n"
    "No markdown. No extra keys. No explanations outside JSON."
)


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


def gemini_validate_batch(
    batch: Sequence[HeadingCandidate],
    *,
    model_label: str = "gemini",
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

    resp = gemini_generate(SYSTEM_INSTRUCTION_VALID, user_prompt)

    parsed: Dict[str, Dict[str, Any]] = {}
    if isinstance(resp.parsed_json, list):
        for item in resp.parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id") or item.get("heading_id")
            is_valid = item.get("is_valid")
            reason = item.get("reason")
            if isinstance(hid, str) and isinstance(is_valid, bool):
                parsed[hid] = {"is_valid": is_valid, "reason": reason if isinstance(reason, str) else ""}
    return parsed, resp.raw_text, request_items


def gemini_validate(
    candidates: Sequence[HeadingCandidate],
    *,
    batch_size: int = 20,
) -> List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]]:
    """
    Returns a list of batches:
      (batch_id, batch_candidates, parsed_by_id, raw_model_text, request_items)
    """
    batches = _chunks(candidates, batch_size)
    out: List[Tuple[int, Sequence[HeadingCandidate], Dict[str, Dict[str, Any]], str, List[Dict[str, Any]]]] = []
    for i, b in enumerate(batches, start=1):
        parsed, raw_text, request_items = gemini_validate_batch(b)
        out.append((i, b, parsed, raw_text, request_items))
    return out

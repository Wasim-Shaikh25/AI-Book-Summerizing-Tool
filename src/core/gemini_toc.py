from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from src.ai.gemini_adapter import gemini_generate
from .models import HeadingCandidate


SYSTEM_INSTRUCTION_TOC = (
    "You are classifying headings as either coming from a PDF Table of Contents (TOC) or as real section headings in the main body.\n"
    "You will be given a list of headings with context previews.\n"
    "A TOC heading is one that appears in the table of contents, often summarizing sections, chapters, or topics, and is not part of the main content flow.\n"
    "A real section heading is part of the main body content and marks the start of a new section, topic, or chapter within the document.\n"
    "Carefully examine the context preview to distinguish between TOC headings and real section headings.\n"
    "Return ONLY a JSON array of objects:\n"
    "[{ \"id\": \"...\", \"is_toc\": true/false, \"reason\": \"...\" }]\n"
    "No markdown. No extra keys. No explanations outside JSON.\n"
    "Do not mark real section headings as TOC. Only mark headings as TOC if they clearly belong to the table of contents.\n"
    "Do not mark section headings as TOC unless there is a clear signal such as appearing in a syllabus, explicit TOC, or summary list. Section headings in the main body should not be marked as TOC."
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
    resp = gemini_generate(SYSTEM_INSTRUCTION_TOC, user_prompt)

    parsed: Dict[str, Dict[str, Any]] = {}
    if isinstance(resp.parsed_json, list):
        for item in resp.parsed_json:
            if not isinstance(item, dict):
                continue
            hid = item.get("id") or item.get("heading_id")
            is_toc = item.get("is_toc")
            reason = item.get("reason")
            if isinstance(hid, str) and isinstance(is_toc, bool):
                parsed[hid] = {"is_toc": is_toc, "reason": reason if isinstance(reason, str) else ""}
    return parsed, resp.raw_text, request_items


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

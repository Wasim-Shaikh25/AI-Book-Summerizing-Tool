import json
from typing import List, Tuple

from src.LLMAdaptor.client import LLMClient
from src.structure.context_builder import build_structural_context
from src.structure.raw_span_builder import RawSpan
from src.utils.debug_logger import debug_log


def build_heading_filter_prompt(
    lines: List[str],
    batch_spans: List[RawSpan],
    model_results: dict | None = None,
) -> Tuple[str, str]:
    # Centralized prompt
    system_prompt = LLMClient.from_config().prompts.get("heading_filter").system

    # Map: span_id -> {"is_valid": bool, "reason": str}
    decisions = {}
    if model_results and isinstance(model_results, dict):
        for item in model_results.get("results", []) or []:
            try:
                sid = int(item.get("span_id"))
            except Exception:
                continue
            decisions[sid] = {
                "is_valid": bool(item.get("is_valid")),
                "reason": str(item.get("reason") or ""),
            }

    headings = []
    for s in batch_spans:
        context_block = build_structural_context(lines, s)

        debug_log(
            "CONTEXT BLOCK FOR SPAN",
            {
                "span_id": s.span_id,
                "context_block": context_block,
            },
        )

        prev_line = lines[s.heading_index - 1] if s.heading_index - 1 >= 0 else ""
        next_line = lines[s.heading_index + 1] if s.heading_index + 1 < len(lines) else ""

        prev_ends_period = bool((prev_line or "").strip().endswith("."))
        next_stripped = (next_line or "").strip()
        next_starts_lower = bool(next_stripped[:1].islower()) if next_stripped else False

        # blank-line separation signals (structural, not semantic)
        blank_before = False
        if s.heading_index - 1 >= 0:
            blank_before = bool((lines[s.heading_index - 1] or "").strip() == "")

        blank_after = False
        if s.heading_index + 1 < len(lines):
            blank_after = bool((lines[s.heading_index + 1] or "").strip() == "")

        d = decisions.get(s.span_id, {"is_valid": False, "reason": ""})

        headings.append(
            {
                "span_id": s.span_id,
                "candidate_heading": s.heading_text,
                "span_word_count": sum(len((ln or "").split()) for ln in s.content_lines),
                "context_block": context_block,
                "previous_line_ends_with_period": prev_ends_period,
                "next_line_starts_lowercase": next_starts_lower,
                "blank_line_before": blank_before,
                "blank_line_after": blank_after,
                # model output being validated
                "is_valid": bool(d.get("is_valid")),
                "reason": str(d.get("reason") or ""),
            }
        )

    user_payload = {
        "batch_id": 0,
        "headings": headings,
    }

    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

    debug_log("HEADING FILTER SYSTEM PROMPT", system_prompt)
    debug_log("HEADING FILTER USER JSON", user_payload)
    debug_log("HEADING FILTER BATCH SPAN IDS", [s.span_id for s in batch_spans])

    return system_prompt, user_prompt

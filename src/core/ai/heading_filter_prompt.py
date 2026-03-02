import json
from typing import List, Tuple

from src.structure.context_builder import build_structural_context
from src.structure.raw_span_builder import RawSpan
from src.utils.debug_logger import debug_log


_HEADING_FILTER_SYSTEM_PROMPT = """You are a document structure analyzer.

Your task is to determine whether a candidate line is a TRUE SECTION HEADING
or part of a paragraph.

You must balance structural patterns with contextual continuity.

-------------------------------------
STRONG HEADING SIGNALS
-------------------------------------

The candidate is likely VALID if:

- It starts with numbering (1., 1.1, I., II., A., etc.)
- It is ALL CAPS and resembles a title
- It ends with ":" and behaves like a section marker
- It is a short noun phrase (not a full explanatory sentence)

-------------------------------------
STRONG INVALID SIGNALS
-------------------------------------

The candidate is INVALID if:

1) next_line_starts_lowercase == true AND blank_line_after == false
   → indicates paragraph continuation

2) The candidate clearly reads as a complete explanatory sentence
   and continues naturally into the next line

3) The context before and after forms continuous prose

-------------------------------------
IMPORTANT
-------------------------------------

Numbered academic headings (e.g., 1.1, 1.2) are VALID
unless they are clearly embedded inside a paragraph.

Do not reject numbered headings solely because they end with a period.

Do not rely only on length.

If structural signals and context conflict:
- Paragraph continuation overrides numbering.
- Otherwise, prefer structural interpretation.

Return JSON only:

{
  "results": [
    {
      "span_id": integer,
      "is_valid": true or false,
      "reason": "brief structural explanation"
    }
  ]
}
"""


def build_heading_filter_prompt(
    lines: List[str],
    batch_spans: List[RawSpan],
    model_results: dict | None = None,
) -> Tuple[str, str]:
    system_prompt = _HEADING_FILTER_SYSTEM_PROMPT

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

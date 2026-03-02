import json
from typing import List, Tuple

from src.structure.raw_span_builder import RawSpan


_HIERARCHY_SYSTEM_PROMPT = """You are a deterministic document hierarchy engine.

You receive validated headings in order.
Your task is to assign:
- a hierarchy level (integer; 1 is highest)
- a parent span_id (or null)

Rules:
1. Numeric patterns define levels:
   - "1" -> level 1
   - "1.1" -> level 2
   - "1.1.1" -> level 3
2. Roman numerals (I, II, III, ...) are high-level sections (usually level 1 or 2).
3. Parent is the nearest previous heading with a LOWER level.
4. Return STRICT JSON ONLY. No prose. No extra keys.

Output JSON format:
{
  "hierarchy": [
    {
      "span_id": integer,
      "level": integer,
      "parent_id": integer or null
    }
  ]
}
"""


def build_hierarchy_prompt(valid_spans: List[RawSpan]) -> Tuple[str, str]:
    system_prompt = _HIERARCHY_SYSTEM_PROMPT

    user_payload = {
        "validated_headings": [
            {"span_id": s.span_id, "title": s.heading_text}
            for s in valid_spans
        ]
    }

    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)
    return system_prompt, user_prompt

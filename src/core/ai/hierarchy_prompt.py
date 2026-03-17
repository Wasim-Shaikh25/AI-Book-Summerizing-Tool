import json
from typing import List, Tuple

from src.LLMAdaptor.client import LLMClient
from src.structure.raw_span_builder import RawSpan


def build_hierarchy_prompt(valid_spans: List[RawSpan]) -> Tuple[str, str]:
    system_prompt = LLMClient.from_config().prompts.get("hierarchy").system

    user_payload = {
        "validated_headings": [
            {"span_id": s.span_id, "title": s.heading_text}
            for s in valid_spans
        ]
    }

    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)
    return system_prompt, user_prompt

from typing import Tuple

from src.LLMAdaptor.client import LLMClient
from src.structure.raw_span_builder import RawSpan


def build_rewrite_prompt(span: RawSpan, previous_overlap_text: str = "") -> Tuple[str, str]:
    system_prompt = LLMClient.from_config().prompts.get("rewrite").system

    title = (span.heading_text or "").strip()
    overlap = (previous_overlap_text or "").strip()
    content = "\n".join(span.content_lines).strip()

    user_prompt = (
        f"SECTION TITLE:\n{title}\n\n"
        f"OVERLAP CONTEXT (may be empty):\n{overlap}\n\n"
        f"CONTENT TO REWRITE:\n{content}\n"
    )

    return system_prompt, user_prompt

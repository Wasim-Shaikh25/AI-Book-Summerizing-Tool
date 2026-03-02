from typing import Tuple

from src.structure.raw_span_builder import RawSpan


_REWRITE_SYSTEM_PROMPT = """You are an academic rewriting engine.

Rules:
- Rewrite ONLY the provided content.
- Do NOT add new facts or external knowledge.
- Preserve the original meaning.
- Use clear academic tone.
- Do NOT explain your changes.
- Output ONLY the rewritten text (no JSON, no headings outside the requested section, no commentary).
"""


def build_rewrite_prompt(span: RawSpan, previous_overlap_text: str = "") -> Tuple[str, str]:
    system_prompt = _REWRITE_SYSTEM_PROMPT

    title = (span.heading_text or "").strip()
    overlap = (previous_overlap_text or "").strip()
    content = "\n".join(span.content_lines).strip()

    user_prompt = (
        f"SECTION TITLE:\n{title}\n\n"
        f"OVERLAP CONTEXT (may be empty):\n{overlap}\n\n"
        f"CONTENT TO REWRITE:\n{content}\n"
    )

    return system_prompt, user_prompt

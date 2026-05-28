"""Rewrite prompt assembly — user instruction is supplied at runtime, not hardcoded."""

from __future__ import annotations

_DEFAULT_SYSTEM = """You are a domain-agnostic academic notes rewriter.
Follow the user's instructions exactly for tone, length, and style.
Technical rules:
1) Use only the provided source text. Do not invent facts.
2) Do not add citations, disclaimers, or meta commentary about the source.
3) Use markdown headings (### Title) and bullets when helpful.
4) Do not wrap the whole answer in a fenced code block.
5) Do not repeat the section title as a bullet point.
"""


def rewrite_system_prompt() -> str:
    return _DEFAULT_SYSTEM


def build_section_user_prompt(*, user_instruction: str, heading: str, source_text: str) -> str:
    instruction = (user_instruction or "").strip()
    if not instruction:
        instruction = "Rewrite the source into clear notes."
    return (
        f"User request:\n{instruction}\n\n"
        f"Section: {heading}\n\n"
        f"Source:\n{source_text}"
    )

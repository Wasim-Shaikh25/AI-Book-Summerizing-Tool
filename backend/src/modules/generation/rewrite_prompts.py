"""Rewrite prompt assembly — user instruction is supplied at runtime, not hardcoded."""

from __future__ import annotations

from typing import Any

_DEFAULT_SYSTEM = """You are a domain-agnostic academic notes rewriter.
Follow the user's instructions exactly for tone, length, and style.
Technical rules:
1) Use only the provided source text. Do not invent facts.
2) Do not add citations, disclaimers, or meta commentary about the source.
3) Use markdown headings (### Title) and bullets when helpful.
4) Do not wrap the whole answer in a fenced code block.
5) Do not repeat the section title as a bullet point.
"""

_EXAM_ORIENTED_SYSTEM = """You write exam-prep study notes in very simple English for quick revision before exams.
Follow the user's instructions exactly.

Required output structure for every section:

### Key Points
- One important fact per bullet; max ~15 words each; plain language a beginner can understand
- Cover ALL important facts, definitions, article numbers, case names, lists, and exceptions from the source
- Do not skip or drop key points from the source

### Quick Revision
- 5–8 ultra-short one-line recall bullets for last-minute review before the exam

Rules:
1) Use ONLY the provided source text. Do not invent facts.
2) Extremely short and to the point — no long paragraphs, no filler, no meta commentary.
3) Simple words — assume the reader is new to the subject.
4) Do not repeat the section title as a bullet.
5) Do not wrap the answer in code fences.
6) If adjacent-section context is provided, use it only for continuity — output notes for the primary section only.
"""

_COMPACT_EXAM_SYSTEM = """You write ULTRA-COMPACT exam cram notes in very simple English.
Follow the user's instructions exactly.

Output structure (ONLY this — no other headings):

### Key Points
- HARD LIMIT: 4–6 bullets total for the entire section
- HARD LIMIT: max 12 words per bullet
- Pick only the most exam-critical facts (definitions, article numbers, key case names, one-line rules)
- Merge related points into one bullet; skip minor examples and repetition
- Plain English a beginner can understand

Rules:
1) Use ONLY the provided source text. Do not invent facts.
2) Do NOT add a Quick Revision section — Key Points alone must be enough for last-minute revision.
3) No paragraphs, no sub-bullets, no filler, no meta commentary.
4) Shorter is better — omit low-value detail even if it appears in the source.
5) Do not wrap the answer in code fences.
6) If adjacent-section context is provided, use it only for continuity — output notes for the primary section only.
7) If the user asks for diagrams, you MAY add ONE simple mermaid flowchart when it clearly helps (valid ```mermaid block only).
"""

_BUNDLED_EXAM_NOTE = """
When rewriting multiple sections in one response:
- Output EVERY section in the bundle, in source order.
- Start each section with: ### {heading} <!-- sid:SXX -->  (exact section_id required)
- Per section: 3–5 short bullets only; do not merge different sections together.
"""


def is_compact_exam_mode() -> bool:
    """Ultra-short exam notes (few bullets, no Quick Revision block)."""
    import os

    return os.environ.get("COMPACT_EXAM", "0").strip().lower() not in {"0", "false", "no", "n"}


def rewrite_system_prompt(*, exam_oriented: bool = False, compact: bool | None = None, bundled: bool = False) -> str:
    compact_mode = is_compact_exam_mode() if compact is None else compact
    if compact_mode and exam_oriented:
        base = _COMPACT_EXAM_SYSTEM
    elif exam_oriented:
        base = _EXAM_ORIENTED_SYSTEM
    else:
        base = _DEFAULT_SYSTEM
    if bundled and exam_oriented:
        return base + _BUNDLED_EXAM_NOTE
    return base


def default_section_max_tokens(
    *,
    exam_oriented: bool = False,
    compact: bool | None = None,
    bundle_size: int = 1,
) -> int:
    compact_mode = is_compact_exam_mode() if compact is None else compact
    per = 450 if compact_mode and exam_oriented else (1200 if exam_oriented else 1800)
    if bundle_size > 1:
        return min(4096, per * bundle_size)
    return per


def build_section_user_prompt(*, user_instruction: str, heading: str, source_text: str) -> str:
    return build_section_user_prompt_with_context(
        user_instruction=user_instruction,
        heading=heading,
        source_text=source_text,
    )


def build_section_user_prompt_with_context(
    *,
    user_instruction: str,
    heading: str,
    source_text: str,
    prev_heading: str = "",
    prev_overlap: str = "",
    next_heading: str = "",
    next_overlap: str = "",
) -> str:
    instruction = (user_instruction or "").strip()
    if not instruction:
        instruction = "Rewrite the source into clear notes."

    parts = [
        f"User request:\n{instruction}\n",
        f"Section to rewrite: {heading}\n",
        f"Primary source (rewrite ONLY this section):\n{source_text}",
    ]

    if prev_overlap:
        label = prev_heading or "Previous section"
        parts.append(
            f"\nContext from previous section (continuity only — do NOT rewrite this part):\n"
            f"[{label}]: {prev_overlap}"
        )
    if next_overlap:
        label = next_heading or "Next section"
        parts.append(
            f"\nContext from next section (continuity only — do NOT rewrite this part):\n"
            f"[{label}]: {next_overlap}"
        )

    parts.append("\nOutput notes for the primary section only.")
    return "\n".join(parts)


def build_bundle_user_prompt(
    *,
    user_instruction: str,
    bundle: Any,
    max_source_chars: int,
) -> str:
    """Prompt for rewriting several sections in one LLM call."""
    instruction = (user_instruction or "").strip() or "Rewrite into compact exam notes."
    parts = [
        f"User request:\n{instruction}\n",
        f"Chapter: {bundle.chapter_heading or 'General'}\n",
        f"Rewrite ALL {len(bundle.sections)} sections below in one response.\n",
        "Use this format for EACH section (exact sid tag required):\n"
        "### {section heading} <!-- sid:SXX -->\n- bullet …\n",
    ]
    for i, sec in enumerate(bundle.sections, start=1):
        sid = str(sec.get("section_id") or "")
        heading = str(sec.get("heading") or "").strip()
        text = str(sec.get("text") or "")[:max_source_chars]
        parts.append(f"--- [{sid}] {heading} ---\n{text}\n")
    return "\n".join(parts)


def is_exam_oriented_mode() -> bool:
    """True when EXAM_ORIENTED env is enabled (default on for pipeline script)."""
    import os

    return os.environ.get("EXAM_ORIENTED", "1").strip().lower() not in {"0", "false", "no", "n"}

"""Rewrite prompt assembly — dynamic format from LLM intent or user instruction."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.modules.interaction.command_parser import IntentResult

_DIAGRAM_KEYWORDS = re.compile(
    r"\b(diagram|diagrams|mermaid|flowchart|flow\s*chart|visual(?:\s+aid)?s?)\b",
    re.I,
)
_EXAM_KEYWORDS = re.compile(
    r"\b(exam[\s-]?oriented|exam[\s-]?prep|exam\s+notes|revision\s+notes|quick\s+revision|"
    r"last[\s-]?(?:minute|moment)|cram\s+notes|last[\s-]?moment\s+prep(?:aration)?)\b"
    r"|(?:\bkey\s+points\b.*\b(?:quick\s+revision|revision)\b)",
    re.I,
)
_COMPACT_KEYWORDS = re.compile(
    r"\b(ultra[\s-]?short|very\s+short|few\s+bullets|4[\s-]?6\s+bullets|cram|last[\s-]?moment)\b",
    re.I,
)
_SHORT_KEYWORDS = re.compile(
    r"\b(short|brief|concise|to\s+the\s+point|no\s+extra)\b",
    re.I,
)
_DETAILED_KEYWORDS = re.compile(
    r"\b(detailed|comprehensive|in[\s-]?depth|elaborate|full\s+notes|cover\s+everything)\b",
    re.I,
)
_PARAGRAPH_PREFERRED_KEYWORDS = re.compile(
    r"\b("
    r"do\s+not\s+use\s+bullet|don'?t\s+use\s+bullet|no\s+bullet|without\s+bullet|avoid\s+bullet|"
    r"only\s+use\s+bullet|bullet\s+only\s+where|paragraph|prose|in\s+paragraph"
    r")\b",
    re.I,
)
_MERMAID_FENCE_FIX = re.compile(
    r"(?<![`])`mermaid\s*\n([\s\S]*?)\n`(?![`])",
    re.I,
)
_BARE_MERMAID_BLOCK = re.compile(
    r"(?:^|\n)mermaid\s*\n((?:\s*\w+.*\n)+)",
    re.I,
)

_GUARDRAILS = """You are a domain-agnostic academic notes rewriter.
Technical rules (always apply):
1) Use only the provided source text. Do not invent facts.
2) Do not add citations, disclaimers, or meta commentary about the source.
3) Do not repeat the section title as a bullet point.
4) Do not wrap the whole answer in a fenced code block (except valid ```mermaid diagram blocks when requested).
5) If adjacent-section context is provided, use it only for continuity — output notes for the primary section only.
6) When a neighbouring section covers a similar topic, include only information unique to this section — no repetition.
7) Output English only — no Hindi, Urdu, Arabic, or other non-English script. Skip or paraphrase non-English source text in simple English.
8) UNIVERSAL MARKDOWN STRUCTURE (always):
   - Section bodies: export adds the ## section title — do NOT repeat it; write body content only.
   - Use ### only for genuine sub-parts with real content (when helpful).
   - Do NOT use standalone **bold** lines as fake subheadings unless the user asked for labeled blocks.
   - Follow the user's request for length, depth, bullets vs prose, and tone — do not artificially shorten or pad.
9) Do NOT include syllabus/admin blocks: course objectives/outcomes, learning outcomes, module/unit labels, reading lists, or "Also cover:" checklists — teach the topic only.
10) "Simple English" means plain words a beginner can understand — NOT artificially short sentences. Do not shorten legal or technical content; explain it clearly.
11) Never write filler such as "This chapter covers…", "This section addresses…", or "In this unit we learn…" — explain the substance from the source only.
12) Do not create a **bold subheading** unless the user explicitly asked for labeled blocks (e.g. Key Points).
13) FORBIDDEN in section body (never output these):
    - Meta filler: "This section/chapter covers…", "We will discuss…", "It is important to note…"
    - Repeating the section title as the first line or as a bullet
    - Syllabus/admin: course outcomes, learning objectives, instructional hours, module/unit labels, reading lists
    - Standalone **bold** lines with no real content underneath
    - Thin bullets: one-word or two-word bullets like "- Yes", "- Important"
    - Content that cannot be traced to the provided source text
14) Write continuous justified prose for main explanations. Use bullet or numbered lists ONLY for genuine enumerations (examples, steps, case lists) — not for the whole section.
15) Do not break one idea into many tiny one-sentence paragraphs. Merge related sentences into proper paragraphs.
"""

# Legacy alias — universal format supersedes book-only addendum.
_BOOK_FORMAT_ADDENDUM = ""

_DIAGRAM_SYSTEM_ADDENDUM = """
DIAGRAM RULES (user requested visual aids):
- Follow the user's note format; do not add extra template sections they did not ask for.
- Add a diagram ONLY for complex processes, hierarchies, or comparisons — skip simple definitions and short sections.
- Maximum about ONE diagram every 8–10 sections (not every section).
- Keep flowcharts tiny: max 4 nodes, short labels (3–5 words each).
- Use ONE ```mermaid fenced block (triple backticks); no separate ### Diagram heading.
- Never use single-backtick fences for diagrams.
"""

_BUNDLED_EXAM_NOTE = """
When rewriting multiple sections in one response:
- Output EVERY section in the bundle, in source order.
- Start each section with: ### {heading} <!-- sid:SXX -->  (exact section_id required)
- Follow the user's requested format per section; do not merge different sections together.
"""

# Legacy templates — only when INTENT_LEGACY_REGEX=1
_DEFAULT_SYSTEM = """You are a domain-agnostic academic notes rewriter.
Follow the user's instructions exactly for structure, tone, length, headings, and style.
Technical rules:
1) Use only the provided source text. Do not invent facts.
2) Do not add citations, disclaimers, or meta commentary about the source.
3) Use the output structure the user asks for (headings, bullets, paragraphs, etc.).
4) Do NOT impose fixed templates such as "Key Points" or "Quick Revision" unless the user explicitly requests them.
5) Match the requested length: short requests stay short; detailed requests include more coverage.
6) Do not wrap the whole answer in a fenced code block (except valid ```mermaid diagram blocks when requested).
7) Do not repeat the section title as a bullet point.
"""

_EXAM_ORIENTED_SYSTEM = """You write exam-prep study notes in very simple English for quick revision before exams.
Follow the user's instructions exactly.

Required output structure for every section (only because the user asked for exam-style notes):

### Key Points
- One important fact per bullet; max ~15 words each; plain language a beginner can understand
- Cover ALL important facts, definitions, key terms, named examples, lists, and exceptions from the source
- Do not skip or drop key points from the source

### Quick Revision
- 5–8 ultra-short one-line recall bullets for last-minute review before the exam

Rules:
1) Use ONLY the provided source text. Do not invent facts.
2) Extremely short and to the point — no long paragraphs, no filler, no meta commentary.
3) Simple words — assume the reader is new to the subject.
4) Do not repeat the section title as a bullet.
5) Do not wrap the answer in code fences (except valid ```mermaid diagram blocks when requested).
6) If adjacent-section context is provided, use it only for continuity — output notes for the primary section only.
"""

_COMPACT_EXAM_SYSTEM = """You write ULTRA-COMPACT exam cram notes in very simple English.
Follow the user's instructions exactly.

Output structure (ONLY this — no other headings):

### Key Points
- HARD LIMIT: 4–6 bullets total for the entire section
- HARD LIMIT: max 12 words per bullet
- Pick only the most exam-critical facts (definitions, key terms, named examples, one-line rules)
- Merge related points into one bullet; skip minor examples and repetition
- Plain English a beginner can understand

Rules:
1) Use ONLY the provided source text. Do not invent facts.
2) Do NOT add a Quick Revision section — Key Points alone must be enough for last-minute revision.
3) No paragraphs, no sub-bullets, no filler, no meta commentary.
4) Shorter is better — omit low-value detail even if it appears in the source.
5) Do not wrap the answer in code fences (except valid ```mermaid diagram blocks when requested).
6) If adjacent-section context is provided, use it only for continuity — output notes for the primary section only.
"""


@dataclass(frozen=True)
class RewriteProfile:
    """Resolved rewrite behaviour from intent, env, or user instruction."""

    exam_oriented: bool
    compact: bool
    include_diagrams: bool
    depth: str
    max_tokens: int


def _env_tri_state(key: str) -> Optional[bool]:
    raw = os.environ.get(key, "").strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return None


def legacy_regex_enabled() -> bool:
    return _env_tri_state("INTENT_LEGACY_REGEX") is True


def _instruction_text(user_instruction: str = "") -> str:
    explicit = (user_instruction or "").strip()
    if explicit:
        return explicit
    for key in ("REWRITE_USER_INSTRUCTION", "REWRITE_ASK", "PIPELINE_REWRITE_ASK"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def build_dynamic_rewrite_system_prompt(
    *,
    user_instruction: str = "",
    intent: Optional["IntentResult"] = None,
) -> str:
    """Guardrails + refined user instruction + refiner output format (no hardcoded templates)."""
    if intent and intent.rewrite_system_prompt.strip():
        return intent.rewrite_system_prompt.strip()

    from src.modules.interaction.command_parser import effective_user_instruction

    instruction = effective_user_instruction(
        intent,
        _instruction_text(user_instruction) or "Rewrite the source into clear notes.",
    )
    include_diagrams = bool(intent.include_diagrams if intent else user_requests_diagrams(user_instruction))

    parts = [_GUARDRAILS, f"\nUser request:\n{instruction}\n"]
    parts.append(
        "\nFollow the user request for structure, tone, length, and style.\n"
        "Do NOT impose fixed templates such as 'Key Points' or 'Quick Revision' "
        "unless the user explicitly requests them.\n"
    )
    if include_diagrams:
        parts.append(_DIAGRAM_SYSTEM_ADDENDUM)
    from src.shared.english_text import english_only_rewrite_instruction

    eng = english_only_rewrite_instruction()
    if eng:
        parts.append(f"\n{eng}\n")
    from src.shared.document_format_style import universal_rewrite_format_addendum

    parts.append(universal_rewrite_format_addendum())
    return "".join(parts)


def user_prefers_paragraphs(user_instruction: str = "") -> bool:
    """True when user wants paragraph-style notes with bullets only where necessary."""
    text = _instruction_text(user_instruction).lower()
    if _PARAGRAPH_PREFERRED_KEYWORDS.search(text):
        return True
    if "bullet" in text and any(p in text for p in ("do not", "don't", "only use", "avoid", "without")):
        return True
    return False


def infer_content_depth(user_instruction: str = "") -> str:
    """Infer desired note length from user wording."""
    text = _instruction_text(user_instruction).lower()
    if _COMPACT_KEYWORDS.search(text):
        return "very_short"
    if _SHORT_KEYWORDS.search(text):
        return "short"
    if _DETAILED_KEYWORDS.search(text):
        return "detailed"
    return "medium"


def user_requests_diagrams(user_instruction: str = "") -> bool:
    """True when the user explicitly asks for diagrams."""
    explicit = (user_instruction or "").strip()
    if explicit:
        return bool(_DIAGRAM_KEYWORDS.search(explicit))
    if _env_tri_state("REWRITE_INCLUDE_DIAGRAMS") is True:
        return True
    return bool(_DIAGRAM_KEYWORDS.search(_instruction_text("")))


def user_requests_exam_notes(user_instruction: str = "") -> bool:
    """True only when the user asks for exam-style templates (legacy regex path)."""
    explicit = (user_instruction or "").strip()
    if explicit:
        return bool(_EXAM_KEYWORDS.search(explicit))
    exam_env = _env_tri_state("EXAM_ORIENTED")
    if exam_env is not None:
        return exam_env
    return bool(_EXAM_KEYWORDS.search(_instruction_text("")))


def user_requests_compact_notes(user_instruction: str = "") -> bool:
    """Ultra-short exam cram sections — legacy regex path only."""
    explicit = (user_instruction or "").strip()
    if explicit:
        if user_requests_diagrams(explicit):
            return False
        if not user_requests_exam_notes(explicit):
            return False
        return bool(_COMPACT_KEYWORDS.search(explicit))
    compact_env = _env_tri_state("COMPACT_EXAM")
    if compact_env is not None:
        return compact_env
    if user_requests_diagrams(""):
        return False
    if not user_requests_exam_notes(""):
        return False
    return bool(_COMPACT_KEYWORDS.search(_instruction_text("")))


def _max_tokens_for_profile(
    *,
    exam_oriented: bool,
    compact: bool,
    include_diagrams: bool,
    depth: str,
    bundle_size: int = 1,
) -> int:
    if exam_oriented and compact:
        per = 450
    elif exam_oriented:
        per = 1200
    elif depth == "very_short":
        per = 500
    elif depth == "short":
        per = 1000
    elif depth == "detailed":
        per = 2800
    else:
        per = 1800
    if include_diagrams:
        per += 400
    if bundle_size > 1:
        return min(4096, per * bundle_size)
    return per


def _depth_from_intent(intent: "IntentResult") -> str:
    depth = (intent.depth or "medium").strip().lower()
    if depth in {"very_short", "short", "medium", "detailed"}:
        return depth
    return "medium"


def _page_adjusted_depth(depth: str) -> str:
    """Large PDFs need slightly richer notes — universal, not subject-specific."""
    import os

    try:
        pages = int(os.environ.get("PIPELINE_PAGE_COUNT", "0") or "0")
    except ValueError:
        pages = 0
    if pages >= 250 and depth in {"very_short", "short"}:
        return "medium"
    if pages >= 120 and depth == "very_short":
        return "short"
    return depth


def resolve_rewrite_profile(
    user_instruction: str = "",
    intent: Optional["IntentResult"] = None,
) -> RewriteProfile:
    """Resolve token limits and flags from LLM intent or legacy keyword heuristics."""
    if intent and intent.routing_method == "llm":
        depth = _page_adjusted_depth(_depth_from_intent(intent))
        diagrams = intent.include_diagrams
        max_tokens = _max_tokens_for_profile(
            exam_oriented=False,
            compact=False,
            include_diagrams=diagrams,
            depth=depth,
        )
        return RewriteProfile(
            exam_oriented=False,
            compact=False,
            include_diagrams=diagrams,
            depth=depth,
            max_tokens=max_tokens,
        )

    if not legacy_regex_enabled():
        instruction = _instruction_text(user_instruction)
        depth = _page_adjusted_depth(infer_content_depth(instruction))
        diagrams = user_requests_diagrams(instruction)
        max_tokens = _max_tokens_for_profile(
            exam_oriented=False,
            compact=False,
            include_diagrams=diagrams,
            depth=depth,
        )
        return RewriteProfile(
            exam_oriented=False,
            compact=False,
            include_diagrams=diagrams,
            depth=depth,
            max_tokens=max_tokens,
        )

    exam = user_requests_exam_notes(user_instruction)
    compact = user_requests_compact_notes(user_instruction) if exam else False
    diagrams = user_requests_diagrams(user_instruction)
    depth = _page_adjusted_depth(infer_content_depth(user_instruction))
    if exam and compact:
        depth = "very_short"
    elif exam and depth == "medium":
        depth = "short"
    max_tokens = _max_tokens_for_profile(
        exam_oriented=exam,
        compact=compact,
        include_diagrams=diagrams,
        depth=depth,
    )
    return RewriteProfile(
        exam_oriented=exam,
        compact=compact,
        include_diagrams=diagrams,
        depth=depth,
        max_tokens=max_tokens,
    )


def is_exam_oriented_mode(*, user_instruction: str = "", intent: Optional["IntentResult"] = None) -> bool:
    if intent and intent.routing_method == "llm":
        return intent.format_type == "exam_oriented"
    return user_requests_exam_notes(user_instruction)


def is_compact_exam_mode(*, user_instruction: str = "", intent: Optional["IntentResult"] = None) -> bool:
    if intent and intent.routing_method == "llm":
        return intent.depth == "very_short"
    return user_requests_compact_notes(user_instruction)


def _legacy_rewrite_system_prompt(
    *,
    exam_oriented: bool,
    compact_mode: bool,
    include_diagrams: bool,
    bundled: bool,
) -> str:
    if exam_oriented and compact_mode:
        base = _COMPACT_EXAM_SYSTEM
    elif exam_oriented:
        base = _EXAM_ORIENTED_SYSTEM
    else:
        base = _DEFAULT_SYSTEM
    if include_diagrams:
        base = base + _DIAGRAM_SYSTEM_ADDENDUM
    if bundled and exam_oriented:
        base = base + _BUNDLED_EXAM_NOTE
    from src.shared.english_text import english_only_rewrite_instruction

    eng = english_only_rewrite_instruction()
    if eng:
        base = base + f"\n{eng}\n"
    return base


def rewrite_system_prompt(
    *,
    exam_oriented: bool | None = None,
    compact: bool | None = None,
    bundled: bool = False,
    user_instruction: str = "",
    include_diagrams: bool | None = None,
    intent: Optional["IntentResult"] = None,
    enforce_single_topic: bool = False,
) -> str:
    profile = resolve_rewrite_profile(user_instruction, intent=intent)

    if intent and intent.routing_method == "llm":
        prompt = build_dynamic_rewrite_system_prompt(user_instruction=user_instruction, intent=intent)
        if bundled:
            prompt = prompt + _BUNDLED_EXAM_NOTE
        if enforce_single_topic:
            prompt += (
                "\nDiscuss only the topic named in the section heading provided to you. "
                "Do not summarise the previous or next section."
            )
        return prompt

    if not legacy_regex_enabled():
        prompt = build_dynamic_rewrite_system_prompt(user_instruction=user_instruction, intent=intent)
        if bundled:
            prompt = prompt + _BUNDLED_EXAM_NOTE
        if enforce_single_topic:
            prompt += (
                "\nDiscuss only the topic named in the section heading provided to you. "
                "Do not summarise the previous or next section."
            )
        return prompt

    exam = profile.exam_oriented if exam_oriented is None else exam_oriented
    compact_mode = profile.compact if compact is None else compact
    if include_diagrams is None:
        include_diagrams = profile.include_diagrams
    prompt = _legacy_rewrite_system_prompt(
        exam_oriented=exam,
        compact_mode=compact_mode,
        include_diagrams=include_diagrams,
        bundled=bundled,
    )
    if enforce_single_topic:
        prompt += (
            "\nDiscuss only the topic named in the section heading provided to you. "
            "Do not summarise the previous or next section."
        )
    return prompt


def normalize_rewritten_section(text: str, *, user_instruction: str = "", heading: str = "", chapter_heading: str = "") -> str:
    """Fix malformed mermaid fences, strict markdown layout, and strip internal sid tags."""
    from src.modules.generation.markdown_format_normalizer import strict_normalize_markdown
    from src.modules.generation.notes_body_postprocess import postprocess_rewritten_section
    from src.modules.generation.rewrite_validation import strip_section_id_tags
    from src.shared.english_text import filter_english_body

    instruction = user_instruction or _instruction_text("")
    out = filter_english_body(strip_section_id_tags((text or "").strip()))
    if not out:
        return out
    out = strict_normalize_markdown(out, user_instruction=instruction)
    out = postprocess_rewritten_section(out, heading=heading, chapter_heading=chapter_heading)
    out = _MERMAID_FENCE_FIX.sub(r"```mermaid\n\1\n```", out)

    def _wrap_bare(match: re.Match[str]) -> str:
        body = (match.group(1) or "").strip()
        if not body or "```" in body:
            return match.group(0)
        return f"\n```mermaid\n{body}\n```"

    if "```mermaid" not in out.lower():
        out = _BARE_MERMAID_BLOCK.sub(_wrap_bare, out, count=1)
    return out


def default_section_max_tokens(
    *,
    exam_oriented: bool | None = None,
    compact: bool | None = None,
    bundle_size: int = 1,
    user_instruction: str = "",
    include_diagrams: bool | None = None,
    depth: str | None = None,
    intent: Optional["IntentResult"] = None,
) -> int:
    profile = resolve_rewrite_profile(user_instruction, intent=intent)
    return _max_tokens_for_profile(
        exam_oriented=profile.exam_oriented if exam_oriented is None else exam_oriented,
        compact=profile.compact if compact is None else compact,
        include_diagrams=profile.include_diagrams if include_diagrams is None else include_diagrams,
        depth=depth or profile.depth,
        bundle_size=bundle_size,
    )


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
    chapter_heading: str = "",
    subheadings: Optional[list[str]] = None,
) -> str:
    from src.modules.generation.rewrite_validation import heading_similarity

    instruction = (user_instruction or "").strip()
    if not instruction:
        instruction = "Rewrite the source into clear notes."

    parts = [
        f"User request:\n{instruction}\n",
    ]
    if chapter_heading:
        parts.append(f"Chapter title (use as context only, do not repeat as heading): {chapter_heading}\n")
    parts.append(f"Section title (use this exact label for the section topic): {heading}\n")
    labels = [s.strip() for s in (subheadings or []) if (s or "").strip()]
    if labels:
        try:
            from src.shared.notes_export_style import is_book_export_style

            book = is_book_export_style()
        except Exception:
            book = False
        if book:
            parts.append(
                "Source sub-labels (weave into prose — do NOT emit as standalone **bold** lines):\n"
                + "\n".join(f"- {label}" for label in labels[:12])
                + "\n"
            )
        else:
            parts.append(
                "Subtopics (use **bold subheading** only when the source has real text for that label; "
                "skip bare chapter/illustration labels):\n"
                + "\n".join(f"- {label}" for label in labels[:12])
                + "\n"
            )
    parts.append(f"Primary source (rewrite ONLY this section):\n{source_text}")

    if prev_heading and heading_similarity(prev_heading, heading) >= 0.72:
        parts.append(
            f"\nIMPORTANT — The previous section '{prev_heading}' covers a closely related topic. "
            "Do NOT repeat its definitions, background, or shared legal principles. "
            "Write ONLY what is unique to THIS section (specific amendment, date, case, or rule)."
        )
    elif next_heading and heading_similarity(next_heading, heading) >= 0.72:
        parts.append(
            f"\nIMPORTANT — The next section '{next_heading}' covers a closely related topic. "
            "Do NOT preview or duplicate its content. Focus only on THIS section's unique points."
        )

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

    try:
        from src.shared.notes_export_style import is_book_export_style

        book = is_book_export_style()
    except Exception:
        book = False
    if book:
        parts.append(
            "\nOutput notes for the primary section only.\n"
            "Write in continuous prose paragraphs (textbook style, justified in export). "
            "Use plain English — explain clearly; do NOT artificially shorten sentences or omit detail.\n"
            "Use bullet or numbered lists ONLY when listing examples, steps, ingredients, or 3+ parallel items.\n"
            "Do NOT repeat the section title. Do NOT write meta filler. Do NOT use standalone **bold** lines.\n"
            "Weave any sub-labels into flowing paragraphs unless a short list of examples is clearer."
        )
    else:
        parts.append(
            "\nOutput notes for the primary section only.\n"
            "Follow the refined user request above. "
            "Put each **bold subheading** and each paragraph or bullet on its own line — never chain with ' - '.\n"
            "Use the section title and subtopic labels provided above — do not invent new parent headings. "
            "Cover every listed subtopic in prose under its **bold** label."
        )
    return "\n".join(parts)


def build_bundle_user_prompt(
    *,
    user_instruction: str,
    bundle: Any,
    max_source_chars: int,
) -> str:
    """Prompt for rewriting several sections in one LLM call."""
    instruction = (user_instruction or "").strip() or "Rewrite the source into clear notes."
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

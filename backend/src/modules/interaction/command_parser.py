import logging
from typing import Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntentResult(BaseModel):
    task_type: str = Field(
        ...,
        description="rewrite_book, summarize_book, study_notes, revision_notes, explain_section, question_answer, export, clarify",
    )
    scope: str = Field(..., description="full_book, specific_topic, single_question")
    depth: str = Field(..., description="very_short, short, medium, detailed")
    language_level: str = Field(..., description="simple, standard, advanced")
    format_type: str = Field(..., description="paragraph, bullet, exam_oriented, free")
    allow_external_knowledge: bool = Field(True)
    normalized_query: str = Field(..., description="A concise, search-optimized version of the user's request.")
    target_topics: list[str] = Field(default_factory=list)
    include_diagrams: bool = Field(False, description="User requested diagrams or flowcharts")
    original_user_input: str = Field(
        default="",
        description="Exact user message before refinement — primary source for rewrite/QA prompts",
    )
    refined_instruction: str = Field(
        default="",
        description="Stage-2 polished instruction for logging/disambiguation; not preferred over original",
    )
    rewrite_format: str = Field(
        default="",
        description="Deprecated — refiner no longer injects output templates",
    )
    rewrite_system_prompt: str = Field(
        default="",
        description="Optional pre-composed system prompt; when empty, built from rewrite_format",
    )
    clarification_message: str = Field(
        default="",
        description="When task_type=clarify, message to show the user",
    )
    routing_method: str = Field(
        default="rules",
        description="llm | rules — how routing was resolved",
    )
    refinement_method: str = Field(
        default="",
        description="openai | openrouter | passthrough — how refined_instruction was produced",
    )


def effective_user_instruction(intent: "IntentResult | None", fallback: str = "") -> str:
    """Instruction passed to rewrite/QA — prefers the user's original message."""
    if intent is None:
        return (fallback or "").strip()
    original = (intent.original_user_input or "").strip()
    if original:
        return original
    fb = (fallback or "").strip()
    if fb:
        return fb
    for val in (intent.normalized_query, intent.refined_instruction):
        if (val or "").strip():
            return val.strip()
    return ""


class CommandParser:
    """Deterministic intent parser (no LLM classification)."""

    def parse_intent(self, user_input: str) -> Optional[Union[IntentResult, str]]:
        user_input = user_input.strip()
        if not user_input:
            return None

        cmd = user_input.lower()
        if cmd in ["exit", "quit"]:
            return "exit"
        if cmd == "help":
            return "help"
        if cmd == "export":
            return "export"

        cmd = user_input.lower()

        depth = "medium"
        language_level = "standard"
        format_type = "paragraph"
        task_type = "rewrite_book"
        allow_external = True

        if any(k in cmd for k in ("very short", "ultra short", "quick revision", "quick prep", "executive summary", "quick reference")):
            depth = "very_short"
            language_level = "simple"
        elif any(k in cmd for k in ("short", "simple", "easy")):
            depth = "short"
            language_level = "simple"

        if any(k in cmd for k in ("revision", "cram", "last minute", "cheat sheet", "key points", "quick reference")):
            task_type = "revision_notes"
            depth = "very_short"
            format_type = "exam_oriented"
            language_level = "simple"
        elif any(k in cmd for k in ("study notes", "exam prep", "exam preparation", "exam oriented", "technical summary", "reference sheet")):
            task_type = "study_notes"
            format_type = "exam_oriented"
            language_level = "simple"

        if any(k in cmd for k in ("rewrite", "full book", "study notes", "revision notes", "summarize")):
            return IntentResult(
                task_type=task_type,
                scope="full_book",
                depth=depth,
                language_level=language_level,
                format_type="exam_oriented" if "exam" in cmd or format_type == "exam_oriented" else format_type,
                allow_external_knowledge=False,
                normalized_query=user_input,
                original_user_input=user_input,
            )

        if cmd.startswith("export book") or cmd.startswith("export full"):
            return IntentResult(
                task_type="rewrite_book",
                scope="full_book",
                depth="medium",
                language_level="standard",
                format_type="exam_oriented",
                allow_external_knowledge=False,
                normalized_query=user_input,
                original_user_input=user_input,
            )

        if cmd.startswith("answer") or cmd.startswith("question") or cmd.startswith("explain") or "?" in user_input:
            return IntentResult(
                task_type="question_answer",
                scope="single_question",
                depth="short" if "short" in cmd else "medium",
                language_level="simple" if "simple" in cmd else "standard",
                format_type="bullet" if "bullet" in cmd else "paragraph",
                allow_external_knowledge=True,
                normalized_query=user_input,
                original_user_input=user_input,
            )

        return IntentResult(
            task_type="question_answer",
            scope="single_question",
            depth="medium",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=True,
            normalized_query=user_input,
            original_user_input=user_input,
        )

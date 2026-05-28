import logging
from typing import Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntentResult(BaseModel):
    task_type: str = Field(..., description="rewrite_book, summarize_book, study_notes, revision_notes, question_answer")
    scope: str = Field(..., description="full_book, specific_topic, single_question")
    depth: str = Field(..., description="very_short, short, medium, detailed")
    language_level: str = Field(..., description="simple, standard, advanced")
    format_type: str = Field(..., description="paragraph, bullet, exam_oriented")
    allow_external_knowledge: bool = Field(True)
    normalized_query: str = Field(..., description="A concise, search-optimized version of the user's request.")
    target_topics: list[str] = Field(default_factory=list)


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

        if any(k in cmd for k in ("rewrite", "full book", "study notes", "revision notes", "summarize")):
            return IntentResult(
                task_type="rewrite_book",
                scope="full_book",
                depth="medium",
                language_level="simple" if "simple" in cmd else "standard",
                format_type="exam_oriented" if "exam" in cmd else "paragraph",
                allow_external_knowledge=False,
                normalized_query=user_input,
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
            )

        if cmd.startswith("answer") or cmd.startswith("question") or "?" in user_input:
            return IntentResult(
                task_type="question_answer",
                scope="single_question",
                depth="medium",
                language_level="standard",
                format_type="paragraph",
                allow_external_knowledge=True,
                normalized_query=user_input,
            )

        return IntentResult(
            task_type="question_answer",
            scope="single_question",
            depth="medium",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=True,
            normalized_query=user_input,
        )

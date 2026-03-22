import logging
from typing import Optional, Union

from pydantic import BaseModel, Field

# Structural reset: Gemini removed.
# from src.core.gemini.client import GeminiClient
# Structural reset: Gemini removed.
# from src.core.gemini.prompts.prompts import PROMPT_CLASSIFY_INTENT

logger = logging.getLogger(__name__)

class IntentResult(BaseModel):
    task_type: str = Field(..., description="rewrite_book, summarize_book, study_notes, revision_notes, question_answer")
    scope: str = Field(..., description="full_book, specific_topic, single_question")
    depth: str = Field(..., description="very_short, short, medium, detailed")
    language_level: str = Field(..., description="simple, standard, advanced")
    format_type: str = Field(..., description="paragraph, bullet, exam_oriented")
    allow_external_knowledge: bool = Field(True)
    normalized_query: str = Field(..., description="A concise, search-optimized version of the user's request.")

class CommandParser:
    """
    Intent Processing Layer.

    Structural reset:
    - LLM-based intent classification is disabled until a replacement is implemented.

    For application runtime, we still allow the CLI to start by using the
    deterministic fallback in `parse_intent`.
    """
    def __init__(self):
        # Intentionally no-op: keep CLI usable without LLM intent classification.
        pass

    def parse_intent(self, user_input: str) -> Optional[Union[IntentResult, str]]:
        """
        Accepts raw user input and returns a structured JSON intent object or a fixed command string.
        """
        user_input = user_input.strip()
        if not user_input:
            return None

        # Handle fixed commands BEFORE any Gemini call
        cmd = user_input.lower()
        if cmd in ["exit", "quit"]:
            return "exit"
        if cmd == "help":
            return "help"
        if cmd == "export":
            return "export"

        # Fallback intent only (no LLM).
        return IntentResult(
            task_type="question_answer",
            scope="single_question",
            depth="medium",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=True,
            normalized_query=user_input,
        )

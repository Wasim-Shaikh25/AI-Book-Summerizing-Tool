import logging
import json
from typing import Tuple, Optional, List, Union
from pydantic import BaseModel, Field, model_validator
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_CLASSIFY_INTENT

logger = logging.getLogger(__name__)

class IntentResult(BaseModel):
    task_type: str = Field(..., description="rewrite_book, summarize_book, study_notes, revision_notes, question_answer")
    scope: str = Field(..., description="full_book, specific_topic, single_question")
    depth: str = Field(..., description="very_short, short, medium, detailed")
    language_level: str = Field(..., description="simple, standard, advanced")
    format_type: str = Field(..., description="paragraph, bullet, exam_oriented")
    allow_external_knowledge: bool = Field(True)
    refers_to_original_structure: bool = Field(False, description="True if user refers to original book structure (e.g., 'Chapter 4', 'Topic 3.2')")
    normalized_query: str = Field(..., description="A concise, search-optimized version of the user's request.")

class CommandParser:
    """
    Intent Processing Layer.
    Uses Gemini ONLY to classify intent and normalize instructions.
    """
    def __init__(self):
        self.client = GeminiClient()

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

        logger.info(f"Processing intent for: '{user_input}'")
        prompt = PROMPT_CLASSIFY_INTENT.format(user_input=user_input)
        
        try:
            # Gemini is NOT allowed to generate content here. Only structured intent JSON.
            result = self.client.generate_content(
                prompt=prompt,
                response_schema=IntentResult
            )
            if isinstance(result, dict) and result:
                return IntentResult.model_validate(result)
            
            # If result is empty or invalid, trigger fallback
            raise ValueError("Empty or invalid intent result from LLM")
        except Exception as e:
            logger.error(f"Intent processing failed: {e}")
            # Fallback intent
            return IntentResult(
                task_type="question_answer",
                scope="single_question",
                depth="medium",
                language_level="standard",
                format_type="paragraph",
                allow_external_knowledge=True,
                normalized_query=user_input
            )

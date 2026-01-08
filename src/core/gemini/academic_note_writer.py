import logging
from typing import List, Dict, Any
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_ACADEMIC_NOTE_WRITER
from src.config import REWRITE_MAX_TOKENS

logger = logging.getLogger(__name__)

class AcademicNoteWriter:
    """
    Writes structured, exam-oriented academic notes in Markdown format.
    Ensures no repetition by cross-referencing already explained topics.
    """
    def __init__(self):
        self.client = GeminiClient()

    def write_notes(
        self, 
        topic_name: str, 
        node_content: str, 
        explanation_depth: str, 
        relationships: List[Dict[str, str]], 
        already_explained: List[str]
    ) -> str:
        """
        Generates Markdown notes for a specific topic.
        """
        logger.info(f"Writing academic notes for topic: {topic_name} (Depth: {explanation_depth})")

        # Format context for the prompt
        rel_context = ", ".join([f"{r['topic']} ({r['relation']})" for r in relationships]) if relationships else "None identified."
        explained_context = ", ".join(already_explained) if already_explained else "None yet."

        prompt = PROMPT_ACADEMIC_NOTE_WRITER.format(
            topic_name=topic_name,
            node_content=node_content,
            explanation_depth=explanation_depth,
            topic_relationships=rel_context,
            already_explained_topics=explained_context
        )

        # Generate Markdown content
        markdown_notes = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.7, "max_output_tokens": REWRITE_MAX_TOKENS * 2}
        )

        if not isinstance(markdown_notes, str):
            logger.warning(f"Failed to generate notes for '{topic_name}'.")
            return ""

        return markdown_notes.strip()

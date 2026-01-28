import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_EXTRACT_BOOK_STRUCTURE
from src.config import REWRITE_MAX_TOKENS

logger = logging.getLogger(__name__)

class StructureNode(BaseModel):
    title: str = Field(..., description="The title of the chapter, section, or subheading.")
    children: Optional[List['StructureNode']] = Field(default_factory=list, description="Sub-sections or subheadings.")

class BookStructure(BaseModel):
    structure: List[StructureNode]

# Required for recursive models in Pydantic v2
StructureNode.model_rebuild()

class StructureExtractor:
    """
    Extracts the hierarchical structure of a book using Gemini.
    """
    def __init__(self, active_model: str = "GEMINI"):
        self.client = GeminiClient()

    def extract_structure(self, full_text: str) -> List[Dict[str, Any]]:
        """
        Extracts the hierarchical Table of Contents (TOC) from the full PDF text.
        This structure serves as a CLOSED SET of fixed structural slots.
        """
        logger.info("Extracting CLOSED SET book structure using Gemini...")
        prompt = PROMPT_EXTRACT_BOOK_STRUCTURE.format(full_text=full_text)
        
        # Use schema-driven generation
        result = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": REWRITE_MAX_TOKENS * 2},
            response_schema=BookStructure
        )

        if not result or "structure" not in result:
            logger.error("Failed to extract book structure or received invalid format.")
            return []

        # The extracted structure is now the authoritative CLOSED SET of slots.
        return result["structure"]

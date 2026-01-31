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
    Extracts the hierarchical structure of a book using Gemini and deduplicates it.
    """
    def __init__(self, active_model: str = "GEMINI"):
        self.client = GeminiClient()

    def _merge_duplicate_nodes(self, nodes: List[StructureNode]) -> List[StructureNode]:
        """
        Recursively merges duplicate nodes in a hierarchical structure.
        Assumes that a "brief" TOC will appear before a "detailed" one.
        """
        if not nodes:
            return []

        seen_titles = {}  # type: Dict[str, StructureNode]
        deduplicated_nodes = []

        for node in nodes:
            normalized_title = node.title.lower().strip()
            if normalized_title in seen_titles:
                # If title seen, append children to the existing node
                existing_node = seen_titles[normalized_title]
                existing_node.children.extend(self._merge_duplicate_nodes(node.children))
            else:
                # If new title, add to seen and process its children
                node.children = self._merge_duplicate_nodes(node.children)
                seen_titles[normalized_title] = node
                deduplicated_nodes.append(node)
        return deduplicated_nodes

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

        # Deduplicate the extracted structure
        structure_nodes = [StructureNode.model_validate(item) for item in result["structure"]]
        deduplicated_structure = self._merge_duplicate_nodes(structure_nodes)

        # Convert back to list of dicts for consistency if needed, or adjust downstream
        return [node.model_dump() for node in deduplicated_structure]

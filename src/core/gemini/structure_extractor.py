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

    def _deduplicate_structure(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Recursively deduplicates nodes with the same title, merging their children.
        """
        seen_titles = {}
        deduplicated = []
        
        for node in nodes:
            title = node['title'].strip()
            # Normalize title for comparison (case-insensitive, strip whitespace)
            norm_title = title.lower()
            
            if norm_title in seen_titles:
                # Merge children if they exist
                existing_node = seen_titles[norm_title]
                if 'children' in node and node['children']:
                    if 'children' not in existing_node or not existing_node['children']:
                        existing_node['children'] = []
                    existing_node['children'].extend(node['children'])
                    # Recursively deduplicate the newly extended children
                    existing_node['children'] = self._deduplicate_structure(existing_node['children'])
            else:
                # New title, add to deduplicated list
                new_node = node.copy()
                if 'children' in new_node and new_node['children']:
                    new_node['children'] = self._deduplicate_structure(new_node['children'])
                seen_titles[norm_title] = new_node
                deduplicated.append(new_node)
                
        return deduplicated

    def extract_structure(self, full_text: str) -> List[Dict[str, Any]]:
        """
        Extracts the hierarchical structure from the full PDF text.
        """
        logger.info("Extracting book structure using Gemini...")
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

        # Apply programmatic deduplication as a safety layer
        return self._deduplicate_structure(result["structure"])

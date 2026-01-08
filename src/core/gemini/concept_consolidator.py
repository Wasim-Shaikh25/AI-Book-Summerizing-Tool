import logging
from typing import List
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_CONSOLIDATE_CONCEPTS
from src.config import REWRITE_MAX_TOKENS

logger = logging.getLogger(__name__)

class ConceptConsolidator:
    """
    Consolidates raw content chunks for a node into a coherent explanation.
    """
    def __init__(self, active_model: str = "GEMINI"):
        self.client = GeminiClient()

    def consolidate_node_content(self, raw_content_list: List[str]) -> str:
        """
        Consolidates a list of raw content chunks for a single structure node.
        """
        if not raw_content_list:
            return ""

        merged_content = "\n\n".join(raw_content_list)
        logger.info(f"Consolidating content for a node (length: {len(merged_content)})...")

        prompt = PROMPT_CONSOLIDATE_CONCEPTS.format(raw_node_content=merged_content)
        
        consolidated_text = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": REWRITE_MAX_TOKENS * 3}
        )
        
        if not isinstance(consolidated_text, str) or not consolidated_text.strip():
            logger.warning("LLM returned empty consolidated text. Falling back to merged raw content.")
            return merged_content
        
        return consolidated_text

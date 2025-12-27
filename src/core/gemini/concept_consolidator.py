import logging
from typing import List, Dict, Any
import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL, ACTIVE_MODEL, REWRITE_MAX_TOKENS
from src.core.gemini.prompts.prompts import PROMPT_CONSOLIDATE_CONCEPTS

logger = logging.getLogger(__name__)

class ConceptConsolidator:
    def __init__(self, active_model: str = ACTIVE_MODEL):
        self.active_model = active_model
        self.gemini_model_name = GEMINI_MODEL

        if self.active_model == "GEMINI":
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found in environment variables.")
            genai.configure(api_key=GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
            logger.info(f"Initializing ConceptConsolidator with Gemini model: {self.gemini_model_name}...")
        else:
            raise ValueError(f"Unsupported active model: {self.active_model}. Only 'GEMINI' is supported.")

    def _generate_text(self, prompt: str, max_tokens: int) -> str:
        """Helper to generate text using the active LLM (Gemini)."""
        try:
            if self.active_model == "GEMINI":
                generation_config = {
                    "max_output_tokens": max_tokens,
                    "temperature": 0.2, # Slightly higher temperature for consolidation, but still focused
                    "top_p": 1,
                    "top_k": 1,
                }
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    stream=False
                )
                if response.candidates and response.candidates[0].content.parts:
                    return response.text.strip()
                else:
                    logger.error(f"Gemini response had no valid text parts. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
                    return ""
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}")
            return ""
        return ""

    def consolidate_node_content(self, raw_content_list: List[str]) -> str:
        """
        Consolidates a list of raw content chunks for a single structure node
        into one coherent explanation, removing redundancy.
        """
        if not raw_content_list:
            logger.debug("Raw content list is empty, returning empty string for consolidation.")
            return ""

        # Merge all raw content for the node
        merged_content = "\n\n".join(raw_content_list)
        
        logger.info(f"Consolidating content for a node (merged text length: {len(merged_content)})...")
        logger.debug(f"Merged content for consolidation:\n{merged_content[:500]}...") # Log first 500 chars

        prompt = PROMPT_CONSOLIDATE_CONCEPTS.format(raw_node_content=merged_content)
        
        # Use a higher token limit for consolidation as it might be a large amount of text
        consolidated_text = self._generate_text(prompt, REWRITE_MAX_TOKENS * 3) # Adjust token limit
        
        if not consolidated_text.strip():
            logger.warning(f"LLM returned empty consolidated text for node. Falling back to merged raw content. (Merged text length: {len(merged_content)})")
            return merged_content # Fallback to original merged content if LLM returns empty
        
        logger.debug(f"Consolidated text from LLM:\n{consolidated_text[:500]}...") # Log first 500 chars
        return consolidated_text

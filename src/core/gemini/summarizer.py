import logging
import sys
from typing import List, Dict, Tuple, Any
import re
import google.generativeai as genai # Import the Gemini client

from src.config import GEMINI_API_KEY, GEMINI_MODEL, ACTIVE_MODEL, REWRITE_MAX_TOKENS
from src.core.gemini.prompts.prompts import PROMPT_REWRITE_CHUNK_SIMPLIFIED, PROMPT_REWRITE_NODE_CONTROLLED

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, active_model: str = ACTIVE_MODEL):
        self.active_model = active_model
        self.gemini_model_name = GEMINI_MODEL

        if self.active_model == "GEMINI":
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found in environment variables.")
            genai.configure(api_key=GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
            logger.info(f"Initializing Summarizer with Gemini model: {self.gemini_model_name}...")
        else:
            raise ValueError(f"Unknown active model: {self.active_model}. Only 'GEMINI' and 'GROK' are supported in this module.")

    def _generate_text(self, prompt: str, max_tokens: int, stream: bool = False) -> str:
        """Helper to generate text using the active LLM (Gemini)."""
        full_response = []
        try:
            if self.active_model == "GEMINI":
                generation_config = {
                    "max_output_tokens": max_tokens,
                    "temperature": 0.7, # You can adjust temperature as needed
                    "top_p": 1,
                    "top_k": 1,
                }
                if stream:
                    response_generator = self.gemini_model.generate_content(
                        prompt,
                        generation_config=generation_config,
                        stream=True
                    )
                    for chunk in response_generator:
                        text_part = chunk.text
                        full_response.append(text_part)
                        sys.stdout.write(text_part)
                        sys.stdout.flush()
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                else:
                    response = self.gemini_model.generate_content(
                        prompt,
                        generation_config=generation_config,
                        stream=False
                    )
                    # Check if response has candidates and text before accessing
                    if response.candidates and response.candidates[0].content.parts:
                        full_response.append(response.text)
                    else:
                        logger.error(f"Gemini response had no valid text parts. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
                        return ""
            
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}")
            return ""
        return "".join(full_response).strip()

    def rewrite_node_controlled(self, node_title: str, node_content: str, explained_concepts: List[str], heading_level: int) -> str:
        """
        Rewrites the consolidated content for a single structure node into structured,
        exam-oriented notes, adhering to strict rules about concept explanation and repetition.
        """
        logger.info(f"Rewriting node: {node_title} (Level {heading_level})")

        # Format explained_concepts for the prompt
        explained_concepts_context = "- " + "\n- ".join(explained_concepts) if explained_concepts else "None yet."
        
        prompt = PROMPT_REWRITE_NODE_CONTROLLED.format(
            node_title=node_title,
            node_content=node_content,
            explained_concepts_context=explained_concepts_context
        )
        
        # Use a higher token limit for rewriting a full node if needed
        rewritten_text = self._generate_text(prompt, REWRITE_MAX_TOKENS * 2, stream=False) # Stream can be true for debugging

        # The prompt now instructs the LLM not to include Markdown headings,
        # so we return the rewritten text directly.
        return rewritten_text

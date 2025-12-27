import logging
import sys
from typing import List, Dict, Tuple, Any
import re
import google.generativeai as genai # Import the Gemini client

from src.config import GEMINI_API_KEY, GEMINI_MODEL, ACTIVE_MODEL, REWRITE_MAX_TOKENS
from src.core.common.prompts import PROMPT_REWRITE_CHUNK, PROMPT_REVISION_NOTES # Import both prompts
from src.core.gemini.prompts.prompts import PROMPT_REWRITE_CHUNK_SIMPLIFIED, PROMPT_REWRITE_NODE_CONTROLLED

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, active_model: str = ACTIVE_MODEL, use_revision_prompt: bool = False):
        self.active_model = active_model
        self.gemini_model_name = GEMINI_MODEL
        self.use_revision_prompt = use_revision_prompt

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
                        raw_response_text = response.text.strip()
                        if not raw_response_text:
                            logger.warning("Gemini response.text was empty after stripping. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                            return ""
                        # Aggressively clean non-printable ASCII characters before returning
                        cleaned_raw_response = ''.join(char for char in raw_response_text if char.isprintable() or char in ['\n', '\t'])
                        full_response.append(cleaned_raw_response)
                    else:
                        logger.error(f"Gemini response had no valid text parts. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                        return ""
            
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}. Raw response: {response.text if response else 'N/A'}")
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
        
        # Select the appropriate prompt based on the toggle
        if self.use_revision_prompt:
            prompt_template = PROMPT_REVISION_NOTES
            logger.info("Using PROMPT_REVISION_NOTES for rewriting.")
        else:
            prompt_template = PROMPT_REWRITE_CHUNK # Assuming PROMPT_REWRITE_CHUNK is the default detailed one
            logger.info("Using PROMPT_REWRITE_CHUNK for rewriting.")

        # The PROMPT_REWRITE_NODE_CONTROLLED prompt is not directly used here,
        # but the structure of the prompt_template should match the expected
        # arguments for .format().
        # For now, I'll use the PROMPT_REWRITE_CHUNK and PROMPT_REVISION_NOTES
        # which expect {additional_context}, {master_brain}, {chunk}.
        # The current rewrite_node_controlled method provides node_title, node_content, explained_concepts.
        # This needs to be reconciled.

        # Let's assume for now that PROMPT_REWRITE_CHUNK and PROMPT_REVISION_NOTES
        # are intended to be used with the same parameters as PROMPT_REWRITE_NODE_CONTROLLED
        # or that the summarizer will handle the context differently.
        # Given the prompt structure in common/prompts.py, it seems PROMPT_REWRITE_CHUNK
        # and PROMPT_REVISION_NOTES are designed for a different context (chunk-based rewriting
        # with master_brain and additional_context).

        # Re-evaluating: The original `rewrite_node_controlled` uses `PROMPT_REWRITE_NODE_CONTROLLED`.
        # The new prompts `PROMPT_REWRITE_CHUNK` and `PROMPT_REVISION_NOTES` are for a different
        # context (chunk-based rewriting with master_brain and additional_context).
        # The task is to switch between "both prompts" for "very short notes".
        # This implies that the `rewrite_node_controlled` method should use either
        # `PROMPT_REWRITE_NODE_CONTROLLED` (for detailed) or `PROMPT_REVISION_NOTES` (for short).
        # I need to ensure `PROMPT_REWRITE_NODE_CONTROLLED` is also imported from common/prompts.py
        # if it's meant to be a common prompt, or keep it in gemini/prompts/prompts.py if it's Gemini-specific.

        # Looking at the original `src/core/gemini/prompts/prompts.py` import,
        # `PROMPT_REWRITE_NODE_CONTROLLED` is imported from there.
        # `PROMPT_REWRITE_CHUNK_SIMPLIFIED` is also there.
        # The user's request was to "make new propmt will be for to create very short notes which can help to revise for students but keeps all main points and some explainations case details intact but very short for the purpose of revision make configuration toggle base so that i can switch between both prompts so keep the existing prompt as it is codes as well"

        # This means I should use `PROMPT_REWRITE_NODE_CONTROLLED` as the "existing prompt"
        # and `PROMPT_REVISION_NOTES` as the "new prompt".
        # Both need to be formatted with `node_title`, `node_content`, `explained_concepts_context`.

        # Let's adjust the imports and prompt selection.
        # I will move PROMPT_REWRITE_NODE_CONTROLLED to common/prompts.py if it's meant to be common,
        # but for now, I'll assume it's fine to import from gemini/prompts/prompts.py and
        # PROMPT_REVISION_NOTES from common/prompts.py.

        # First, I need to ensure PROMPT_REWRITE_NODE_CONTROLLED is available in common/prompts.py
        # or that I can use it directly.
        # The current import is: `from src.core.gemini.prompts.prompts import PROMPT_REWRITE_CHUNK_SIMPLIFIED, PROMPT_REWRITE_NODE_CONTROLLED`
        # I added `from src.core.common.prompts import PROMPT_REWRITE_CHUNK, PROMPT_REVISION_NOTES`
        # This means I have both.

        # The `rewrite_node_controlled` method is the one that needs to switch prompts.
        # The `PROMPT_REWRITE_NODE_CONTROLLED` is the "existing code and prompt as it is".
        # The `PROMPT_REVISION_NOTES` is the "new prompt".

        # Let's use `PROMPT_REWRITE_NODE_CONTROLLED` as the default and `PROMPT_REVISION_NOTES` when `use_revision_prompt` is True.
        # Both prompts need to accept the same `.format()` arguments.
        # `PROMPT_REWRITE_NODE_CONTROLLED` currently takes `node_title`, `node_content`, `explained_concepts_context`.
        # `PROMPT_REVISION_NOTES` currently takes `additional_context`, `master_brain`, `chunk`.
        # This is a mismatch.

        # I need to modify `PROMPT_REVISION_NOTES` in `src/core/common/prompts.py`
        # to accept `node_title`, `node_content`, `explained_concepts_context`
        # or modify the `rewrite_node_controlled` method to provide `additional_context`, `master_brain`, `chunk`.

        # The task states: "make new propmt will be for to create very short notes which can help to revise for students but keeps all main points and some explainations case details intact but very short for the purpose of revision make configuration toggle base so that i can switch between both prompts so keep the existing prompt as it is codes as well"

        # This implies that the new prompt should be used in the same context as the existing one.
        # The existing prompt is `PROMPT_REWRITE_NODE_CONTROLLED`.
        # So, `PROMPT_REVISION_NOTES` needs to be adapted to fit the `rewrite_node_controlled` method's parameters.

        # I will modify `PROMPT_REVISION_NOTES` in `src/core/common/prompts.py` to accept
        # `node_title`, `node_content`, `explained_concepts_context`.
        # This will require another `replace_in_file` call.

        # For now, I will complete the change in `src/core/gemini/summarizer.py` assuming
        # `PROMPT_REVISION_NOTES` will be updated to match the parameter signature.

        selected_prompt = PROMPT_REWRITE_NODE_CONTROLLED
        if self.use_revision_prompt:
            selected_prompt = PROMPT_REVISION_NOTES
            logger.info("Using PROMPT_REVISION_NOTES for rewriting.")
        else:
            logger.info("Using PROMPT_REWRITE_NODE_CONTROLLED for rewriting.")

        prompt = selected_prompt.format(
            node_title=node_title,
            node_content=node_content,
            explained_concepts_context=explained_concepts_context
        )
        
        # Use a higher token limit for rewriting a full node if needed
        rewritten_text = self._generate_text(prompt, REWRITE_MAX_TOKENS * 2, stream=False) # Stream can be true for debugging

        # The prompt now instructs the LLM not to include Markdown headings,
        # so we return the rewritten text directly.
        return rewritten_text

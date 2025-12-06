import logging
import sys
from typing import List, Dict, Tuple, Any
import re
import google.generativeai as genai # Import the Gemini client

from src.config import GEMINI_API_KEY, GEMINI_MODEL, ACTIVE_MODEL, CORE_IDEAS_MAX_TOKENS, MASTER_SUMMARY_MAX_TOKENS, REWRITE_MAX_TOKENS
from src.core.common.prompts import PROMPT_CORE_IDEAS, PROMPT_MASTER_BRAIN_COMBINE_BLOCKS, PROMPT_MASTER_BRAIN_FINAL, PROMPT_REWRITE_CHUNK

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
            raise ValueError(f"Unknown active model: {self.active_model}. Only 'GEMINI' is supported in this module.")

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
                    full_response.append(response.text)
            
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}")
            return ""
        return "".join(full_response).strip()

    def extract_core_ideas(self, chunk: str) -> str:
        """Extracts core ideas from a text chunk using the active LLM."""
        prompt = PROMPT_CORE_IDEAS.format(text=chunk)
        return self._generate_text(prompt, CORE_IDEAS_MAX_TOKENS)

    def create_master_brain(self, core_ideas_list: List[str]) -> str:
        """Combines and compresses core ideas into a master knowledge brain using the active LLM."""
        logger.info("Creating master brain (compressing core ideas)...")
        if not core_ideas_list:
            return ""

        combined_blocks: List[str] = []
        block_size = 30 # Number of core ideas to combine in one go
        for i in range(0, len(core_ideas_list), block_size):
            block = "\n\n".join(core_ideas_list[i:i + block_size])
            prompt = PROMPT_MASTER_BRAIN_COMBINE_BLOCKS.format(text=block)
            combined = self._generate_text(prompt, MASTER_SUMMARY_MAX_TOKENS)
            combined_blocks.append(combined)

        # Final combine
        final_text = "\n\n".join(combined_blocks)
        prompt_final = PROMPT_MASTER_BRAIN_FINAL.format(text=final_text)
        master = self._generate_text(prompt_final, MASTER_SUMMARY_MAX_TOKENS)
        logger.info("Master brain created.")
        return master

    def _remove_prompt_from_output(self, generated_text: str, prompt_template: str, master_brain: str, chunk: str) -> str:
        """
        Removes the formatted prompt and any leading conversational filler from the generated text.
        """
        formatted_prompt = prompt_template.format(master_brain=master_brain, chunk=chunk)
        
        # 1. Attempt to remove the initial instructional part of the prompt
        first_instruction_line = PROMPT_REWRITE_CHUNK.split('\n')[0].strip()
        if generated_text.startswith(first_instruction_line):
            generated_text = generated_text[len(first_instruction_line):].strip()
        
        # Remove any "DO NOT include..." instruction if it appears
        generated_text = re.sub(r"DO NOT include any part of this prompt in your output\. ONLY provide the structured notes\.", "", generated_text, flags=re.IGNORECASE).strip()

        lines = generated_text.split('\n')
        cleaned_lines = []
        content_start_found = False

        # Define patterns that indicate the start of actual content
        content_start_patterns = [
            r"^###\s*Chapter Title:",
            r"^\*\*Summary:\*\*",
            r"^####\s*Topics:",
            r"^\*\*.*?\*\*:", # Matches **Topic Title:**
            r"^- ", # Matches bullet points
            r"^\d+\.\s", # Matches numbered lists, common for examples
            r"^```", # Matches start of code blocks or tables
            r"^\s*\S+" # Any non-empty line (as a last resort)
        ]
        
        # Pattern to identify unwanted "Chapter X ... Page Y" lines generated by the model
        unwanted_chapter_page_pattern = r"^Chapter\s+\d+\s+\.\.\.\s+Page\s+\d+"

        for line in lines:
            stripped_line = line.strip()
            if not content_start_found:
                is_content_start = False
                for pattern in content_start_patterns:
                    if re.match(pattern, stripped_line):
                        is_content_start = True
                        break
                
                # Also check if it's an unwanted "Chapter X ... Page Y" line
                if re.match(unwanted_chapter_page_pattern, stripped_line):
                    logger.debug(f"Skipping unwanted chapter/page line: {stripped_line}")
                    continue

                if is_content_start:
                    cleaned_lines.append(line) # Include this line as it's the start of content
                    content_start_found = True
                elif stripped_line: # If it's not empty, but also not a content start pattern, it might be filler
                    logger.debug(f"Skipping potential prompt/filler line: {stripped_line[:100]}...")
                    continue
                else: # It's an empty line before content, skip it
                    continue
            else:
                cleaned_lines.append(line)
        
        cleaned_text = "\n".join(cleaned_lines).strip()
        
        if not cleaned_text and generated_text:
            logger.warning("Aggressive prompt cleaning resulted in empty notes. Returning original raw output.")
            return generated_text # Fallback to original if cleaning removes everything
        
        return cleaned_text

    def rewrite_chunk_to_structured_notes(self, chunk: str, master_brain: str, additional_context: str = "") -> str:
        """
        Rewrites a text chunk into structured text notes using the active LLM.
        """
        # If additional_context is provided, format it as a prompt instruction
        if additional_context:
            formatted_context = f"Consider the following specific instruction: {additional_context}\n\n"
        else:
            formatted_context = ""

        raw_notes_prompt = PROMPT_REWRITE_CHUNK.format(
            master_brain=master_brain,
            chunk=chunk,
            additional_context=formatted_context
        )
        # Stream the output for the main rewrite process
        return self._generate_text(raw_notes_prompt, REWRITE_MAX_TOKENS, stream=True)

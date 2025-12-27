import logging
import json
from typing import List, Dict, Any, Tuple
import google.generativeai as genai
import re

from src.config import GEMINI_API_KEY, GEMINI_MODEL, ACTIVE_MODEL, REWRITE_MAX_TOKENS
from src.core.gemini.prompts.prompts import PROMPT_EXTRACT_BOOK_STRUCTURE

logger = logging.getLogger(__name__)

class StructureExtractor:
    def __init__(self, active_model: str = ACTIVE_MODEL):
        self.active_model = active_model
        self.gemini_model_name = GEMINI_MODEL

        if self.active_model == "GEMINI":
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found in environment variables.")
            genai.configure(api_key=GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
            logger.info(f"Initializing StructureExtractor with Gemini model: {self.gemini_model_name}...")
        else:
            raise ValueError(f"Unsupported active model: {self.active_model}. Only 'GEMINI' is supported.")

    def _generate_text(self, prompt: str, max_tokens: int) -> str:
        """Helper to generate text using the active LLM (Gemini)."""
        try:
            if self.active_model == "GEMINI":
                generation_config = {
                    "max_output_tokens": max_tokens,
                    "temperature": 0.1, # Lower temperature for structure extraction
                    "top_p": 1,
                    "top_k": 1,
                }
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    stream=False
                )
                # Prioritize response.text as it's a direct string, more robust
                if response.text:
                    raw_response_text = response.text.strip()
                    if not raw_response_text:
                        logger.warning("Gemini response.text was empty after stripping. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                        return ""
                    # Aggressively clean non-printable ASCII characters before JSON parsing
                    cleaned_raw_response = ''.join(char for char in raw_response_text if char.isprintable() or char in ['\n', '\t'])
                    return cleaned_raw_response
                elif response.candidates and response.candidates[0].content.parts:
                    raw_response_text = response.candidates[0].text.strip()
                    if not raw_response_text:
                        logger.warning("Gemini response.candidates[0].text was empty after stripping. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                        return ""
                    # Aggressively clean non-printable ASCII characters before JSON parsing
                    cleaned_raw_response = ''.join(char for char in raw_response_text if char.isprintable() or char in ['\n', '\t'])
                    return cleaned_raw_response
                else:
                    logger.error(f"Gemini response had no valid text parts. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                    return ""
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}. Raw response: {response.text if response else 'N/A'}")
            return ""

    def extract_structure(self, full_text: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Extracts the hierarchical structure (chapters, sections, subheadings)
        from the full PDF text using an LLM.
        The output is a list of dictionaries representing the book's structure.
        Includes retry logic for robustness.
        """
        logger.info("Extracting book structure using LLM...")
        prompt = PROMPT_EXTRACT_BOOK_STRUCTURE.format(full_text=full_text)
        
        for attempt in range(max_retries):
            logger.info(f"Attempt {attempt + 1}/{max_retries} to extract book structure.")
            raw_llm_response = self._generate_text(prompt, REWRITE_MAX_TOKENS * 2) # Increased token limit

            if not raw_llm_response:
                logger.warning("LLM returned empty response for structure extraction.")
                continue

            # Use regex to extract the JSON part, in case the LLM adds conversational text or markdown fences
            json_match = re.search(r'```json\s*(\[.*\])\s*```', raw_llm_response, re.DOTALL)
            if json_match:
                raw_structure_json = json_match.group(1)
                logger.info("Extracted JSON using regex.")
            else:
                # If no markdown fences, try to find the outermost JSON array or object
                json_start_index = -1
                json_end_index = -1
                
                # Try to find an array first
                array_start = raw_llm_response.find('[')
                array_end = raw_llm_response.rfind(']')
                
                # Try to find an object second
                object_start = raw_llm_response.find('{')
                object_end = raw_llm_response.rfind('}')

                if array_start != -1 and array_end != -1 and array_start < array_end:
                    json_start_index = array_start
                    json_end_index = array_end
                elif object_start != -1 and object_end != -1 and object_start < object_end:
                    json_start_index = object_start
                    json_end_index = object_end

                if json_start_index != -1 and json_end_index != -1:
                    raw_structure_json = raw_llm_response[json_start_index : json_end_index + 1].strip()
                    logger.info("Extracted JSON using robust delimiter finding.")
                else:
                    # Fallback: if no clear delimiters, assume the whole response is JSON or try stripping "json" prefix
                    raw_structure_json = raw_llm_response.strip()
                    if raw_structure_json.startswith("json"):
                        raw_structure_json = raw_structure_json[4:].strip()
                    logger.info("No JSON markdown fences or clear delimiters found, attempting to parse raw response as JSON directly.")

            try:
                # The LLM is expected to return a JSON string
                structure = json.loads(raw_structure_json)
                logger.info(f"Successfully extracted book structure with {len(structure)} top-level nodes.")
                return structure
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON structure from LLM response on attempt {attempt + 1}: {e}")
                logger.error(f"Raw LLM response (first 500 chars): {raw_llm_response[:500]}...")
                # If it's the last attempt, log the full response
                if attempt == max_retries - 1:
                    logger.error(f"Full raw LLM response: {raw_llm_response}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during structure extraction on attempt {attempt + 1}: {e}")
                logger.error(f"Raw LLM response (first 500 chars): {raw_llm_response[:500]}...")
                if attempt == max_retries - 1:
                    logger.error(f"Full raw LLM response: {raw_llm_response}")
        
        logger.error(f"Failed to extract book structure after {max_retries} attempts.")
        return []

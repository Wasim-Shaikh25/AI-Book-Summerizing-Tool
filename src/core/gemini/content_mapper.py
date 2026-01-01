import logging
import json
import re # Added for regex parsing
from typing import List, Dict, Any, Tuple
import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL, ACTIVE_MODEL, REWRITE_MAX_TOKENS
from src.core.gemini.prompts.prompts import PROMPT_MAP_CHUNK_TO_STRUCTURE

logger = logging.getLogger(__name__)

class ContentMapper:
    def __init__(self, active_model: str = ACTIVE_MODEL):
        self.active_model = active_model
        self.gemini_model_name = GEMINI_MODEL

        if self.active_model == "GEMINI":
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found in environment variables.")
            genai.configure(api_key=GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel(self.gemini_model_name)
            logger.info(f"Initializing ContentMapper with Gemini model: {self.gemini_model_name}...")
        else:
            raise ValueError(f"Unsupported active model: {self.active_model}. Only 'GEMINI' is supported.")

    def _generate_text(self, prompt: str, max_tokens: int) -> str:
        """Helper to generate text using the active LLM (Gemini)."""
        try:
            if self.active_model == "GEMINI":
                generation_config = {
                    "max_output_tokens": max_tokens,
                    "temperature": 0.1, # Low temperature for mapping
                    "top_p": 1,
                    "top_k": 1,
                }
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    stream=False
                )
                if response.candidates and response.candidates[0].content.parts:
                    raw_response_text = response.text.strip()
                    if not raw_response_text:
                        logger.warning(f"Gemini response.text was empty after stripping. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                        return ""

                    # Aggressively clean non-printable ASCII characters before JSON parsing
                    cleaned_raw_response = ''.join(char for char in raw_response_text if char.isprintable() or char in ['\n', '\t'])
                    
                    extracted_json_text = ""
                    
                    extracted_json_text = ""
                    
                    # Strategy 1: Extract JSON content within markdown fences
                    json_match = re.search(r"```json\s*(.*?)\s*```", cleaned_raw_response, re.DOTALL)
                    if json_match:
                        extracted_json_text = json_match.group(1).strip()
                    
                    # Strategy 2: If markdown fences fail, try to find the first complete and valid JSON object or array
                    if not extracted_json_text:
                        # Iterate through the response to find potential JSON start points
                        for i in range(len(cleaned_raw_response)):
                            if cleaned_raw_response[i] == '{' or cleaned_raw_response[i] == '[':
                                # Attempt to find the matching end brace/bracket
                                balance = 0
                                for j in range(i, len(cleaned_raw_response)):
                                    char = cleaned_raw_response[j]
                                    if char == '{' or char == '[':
                                        balance += 1
                                    elif char == '}' or char == ']':
                                        balance -= 1
                                    
                                    if balance == 0:
                                        candidate = cleaned_raw_response[i : j + 1].strip()
                                        try:
                                            json.loads(candidate) # Validate if it's actual JSON
                                            extracted_json_text = candidate
                                            break # Found a valid JSON, stop searching
                                        except json.JSONDecodeError:
                                            # This balanced block was not valid JSON, continue searching
                                            pass
                                if extracted_json_text: # If a valid JSON was found in this outer loop, break
                                    break
                    
                    if not extracted_json_text:
                        logger.warning(f"LLM response did not contain any parsable JSON. Raw response: {cleaned_raw_response[:500]}...")
                        return "" # Return empty if no valid JSON block is found

                    return extracted_json_text
                else:
                    logger.error(f"Gemini response had no valid text parts. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}. Full response object: {response}")
                    return ""
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}. Raw response: {response.text if response else 'N/A'}")
            return ""

    def _flatten_structure(self, structure: List[Dict[str, Any]], parent_title: str = "", level: int = 0) -> List[Dict[str, Any]]:
        """Flattens the hierarchical structure into a list of nodes with full paths."""
        flat_structure = []
        for node in structure:
            current_title = f"{parent_title} > {node['title']}" if parent_title else node['title']
            flat_structure.append({"title": current_title, "original_node": node, "level": level})
            if "children" in node and node["children"]:
                flat_structure.extend(self._flatten_structure(node["children"], current_title, level + 1))
        return flat_structure

    def map_chunks_to_structure(self, chunks: List[str], book_structure: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Maps each chunk to the most relevant node(s) in the book structure.
        Returns the book_structure with 'raw_content' added to each node.
        """
        logger.info("Mapping chunks to book structure nodes...")
        
        # Create a deep copy of the structure to add content to
        structured_book_with_content = json.loads(json.dumps(book_structure))

        # Flatten the structure for easier LLM prompting and lookup
        flat_structure = self._flatten_structure(structured_book_with_content)
        logger.debug(f"Flat structure titles for mapping: {[node['title'] for node in flat_structure]}")
        
        # Create a mapping from flat title to the actual node object in the hierarchical structure
        # This is a bit tricky with deep copies, so we'll use a recursive helper to find the node
        def find_node_by_path(structure_nodes, path_parts):
            if not path_parts:
                return None
            
            target_title_part = path_parts[0].strip()
            # Remove leading numbering (e.g., "1.", "1.1", "A.", "I.") from the target title part
            target_title_part = re.sub(r"^((\d+\.)+|\w+\.)\s*", "", target_title_part).lower()

            for node in structure_nodes:
                node_title_normalized = node['title'].strip()
                # Remove leading numbering from the node title for comparison
                node_title_normalized = re.sub(r"^((\d+\.)+|\w+\.)\s*", "", node_title_normalized).lower()
                
                # logger.debug(f"Comparing target '{target_title_part}' with node '{node_title_normalized}'") # Debugging line

                if node_title_normalized == target_title_part:
                    if len(path_parts) == 1:
                        return node
                    elif 'children' in node and node['children']:
                        return find_node_by_path(node['children'], path_parts[1:])
            return None

        for i, chunk_content in enumerate(chunks):
            logger.info(f"  Mapping chunk {i + 1}/{len(chunks)}")
            
            # Prepare structure context for the prompt
            structure_titles = "\n".join([f"- {node['title']}" for node in flat_structure])

            prompt = PROMPT_MAP_CHUNK_TO_STRUCTURE.format(
                book_structure_titles=structure_titles,
                chunk_text=chunk_content
            )
            
            # The LLM should return a JSON list of titles this chunk maps to
            # Increased token limit to allow for larger JSON responses
            raw_mapping_json = self._generate_text(prompt, REWRITE_MAX_TOKENS * 2) 

            if not raw_mapping_json.strip():
                logger.warning(f"LLM returned empty response for chunk {i+1} mapping. Skipping JSON decoding.")
                continue # Skip to the next chunk if no JSON was returned

            # Attempt to fix common JSON issues before parsing
            # Remove trailing commas in objects/arrays that might cause errors
            cleaned_json_string = re.sub(r',\s*([\]}])', r'\1', raw_mapping_json)
            
            try:
                mapped_data = json.loads(cleaned_json_string)
                if not isinstance(mapped_data, list):
                    logger.warning(f"LLM did not return a JSON list for chunk {i+1} mapping. Raw response: {cleaned_json_string}")
                    # Fallback: If not a list, try to map the entire chunk to the first top-level node
                    if structured_book_with_content and len(structured_book_with_content) > 0:
                        first_top_node = structured_book_with_content[0]
                        if 'raw_content' not in first_top_node:
                            first_top_node['raw_content'] = []
                        first_top_node['raw_content'].append(chunk_content)
                        logger.warning(f"Fallback: Mapped chunk {i+1} to top-level node '{first_top_node['title']}' due to malformed LLM response.")
                    continue # Skip to the next chunk
                
                for item in mapped_data:
                    if not isinstance(item, dict) or 'title' not in item or 'source_text' not in item:
                        logger.warning(f"Invalid item in LLM mapping response for chunk {i+1}: {item}. Raw response: {cleaned_json_string}")
                        # Fallback for invalid item: map to the first top-level node
                        if structured_book_with_content and len(structured_book_with_content) > 0:
                            first_top_node = structured_book_with_content[0]
                            if 'raw_content' not in first_top_node:
                                first_top_node['raw_content'] = []
                            first_top_node['raw_content'].append(chunk_content)
                            logger.warning(f"Fallback: Mapped chunk {i+1} to top-level node '{first_top_node['title']}' due to invalid item in LLM response.")
                        continue

                    mapped_title = item['title']
                    source_text = item['source_text']

                    # Reconstruct path parts from the flattened title
                    path_parts = mapped_title.split(' > ')
                    target_node = find_node_by_path(structured_book_with_content, path_parts)
                    
                    if target_node:
                        if 'raw_content' not in target_node:
                            target_node['raw_content'] = []
                        # Append the extracted source_text, or the whole chunk_content if source_text is empty
                        if source_text:
                            target_node['raw_content'].append(source_text)
                        else:
                            logger.warning(f"LLM returned empty source_text for mapped title '{mapped_title}'. Using entire chunk_content as fallback.")
                            target_node['raw_content'].append(chunk_content)
                    else:
                        logger.warning(f"Chunk {i+1} mapped to non-existent title: {mapped_title}. Using entire chunk_content as fallback to first top-level node.")
                        # Fallback for non-existent title: map to the first top-level node
                        if structured_book_with_content and len(structured_book_with_content) > 0:
                            first_top_node = structured_book_with_content[0]
                            if 'raw_content' not in first_top_node:
                                first_top_node['raw_content'] = []
                            first_top_node['raw_content'].append(chunk_content)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON mapping from LLM response for chunk {i+1}: {e}")
                logger.error(f"Raw LLM response: {raw_mapping_json}")
                # Fallback for JSONDecodeError: map entire chunk to the first top-level node
                if structured_book_with_content and len(structured_book_with_content) > 0:
                    first_top_node = structured_book_with_content[0]
                    if 'raw_content' not in first_top_node:
                        first_top_node['raw_content'] = []
                    first_top_node['raw_content'].append(chunk_content)
                    logger.warning(f"Fallback: Mapped chunk {i+1} to top-level node '{first_top_node['title']}' due to JSONDecodeError.")
            except Exception as e:
                logger.error(f"An unexpected error occurred during chunk mapping for chunk {i+1}: {e}")
                # Fallback for any other unexpected error: map entire chunk to the first top-level node
                if structured_book_with_content and len(structured_book_with_content) > 0:
                    first_top_node = structured_book_with_content[0]
                    if 'raw_content' not in first_top_node:
                        first_top_node['raw_content'] = []
                    first_top_node['raw_content'].append(chunk_content)
                    logger.warning(f"Fallback: Mapped chunk {i+1} to top-level node '{first_top_node['title']}' due to unexpected error.")
        
        logger.info("Finished mapping chunks to structure nodes.")
        return structured_book_with_content

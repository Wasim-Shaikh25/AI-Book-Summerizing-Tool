import logging
import json
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
                    # Remove markdown fences if present
                    cleaned_text = response.text.strip()
                    if cleaned_text.startswith("```json") and cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[len("```json"): -len("```")].strip()
                    return cleaned_text
                else:
                    logger.error(f"Gemini response had no valid text parts. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
                    return ""
        except Exception as e:
            logger.error(f"Error generating text with {self.active_model}: {e}")
            return ""
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
        
        # Create a mapping from flat title to the actual node object in the hierarchical structure
        # This is a bit tricky with deep copies, so we'll use a recursive helper to find the node
        def find_node_by_path(structure_nodes, path_parts):
            if not path_parts:
                return None
            for node in structure_nodes:
                if node['title'] == path_parts[0]:
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
            raw_mapping_json = self._generate_text(prompt, REWRITE_MAX_TOKENS // 2) # Adjust token limit

            try:
                mapped_data = json.loads(raw_mapping_json)
                if not isinstance(mapped_data, list):
                    raise ValueError("LLM did not return a JSON list for chunk mapping.")
                
                for item in mapped_data:
                    if not isinstance(item, dict) or 'title' not in item or 'source_text' not in item:
                        logger.warning(f"Invalid item in LLM mapping response for chunk {i+1}: {item}")
                        continue

                    mapped_title = item['title']
                    source_text = item['source_text']

                    # Reconstruct path parts from the flattened title
                    path_parts = mapped_title.split(' > ')
                    target_node = find_node_by_path(structured_book_with_content, path_parts)
                    
                    if target_node:
                        if 'raw_content' not in target_node:
                            target_node['raw_content'] = []
                        # Append the extracted source_text, not the whole chunk_content
                        if source_text: # Only add if source_text is not empty
                            target_node['raw_content'].append(source_text)
                    else:
                        logger.warning(f"Chunk {i+1} mapped to non-existent title: {mapped_title}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON mapping from LLM response for chunk {i+1}: {e}")
                logger.error(f"Raw LLM response: {raw_mapping_json}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during chunk mapping for chunk {i+1}: {e}")
        
        logger.info("Finished mapping chunks to structure nodes.")
        return structured_book_with_content

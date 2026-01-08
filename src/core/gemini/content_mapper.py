import logging
import json
import re
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_MAP_CHUNK_TO_STRUCTURE
from src.config import REWRITE_MAX_TOKENS

logger = logging.getLogger(__name__)

class MappedItem(BaseModel):
    title: str = Field(..., description="The exact title of the structure node.")
    source_text: str = Field(..., description="Relevant sentences/paragraphs from the chunk.")

class MappedContent(BaseModel):
    mappings: List[MappedItem]

class ContentMapper:
    """
    Maps content chunks to structure nodes using Gemini.
    """
    def __init__(self, active_model: str = "GEMINI"):
        self.client = GeminiClient()

    def _flatten_structure(self, structure: List[Dict[str, Any]], parent_title: str = "") -> List[Dict[str, Any]]:
        flat_structure = []
        for node in structure:
            current_title = f"{parent_title} > {node['title']}" if parent_title else node['title']
            flat_structure.append({"title": current_title, "original_node": node})
            if "children" in node and node["children"]:
                flat_structure.extend(self._flatten_structure(node["children"], current_title))
        return flat_structure

    def map_chunks_to_structure(self, chunks: List[str], book_structure: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Maps content chunks to structure nodes. 
        NOTE: This modifies the structure by adding 'raw_content' to nodes.
        """
        logger.info("Mapping chunks to book structure nodes using Gemini...")
        
        # We work directly on the provided structure to allow accumulation
        structured_book_with_content = book_structure
        flat_structure = self._flatten_structure(structured_book_with_content)
        
        def find_node_by_path(structure_nodes, path_parts):
            if not path_parts: return None
            target_title = re.sub(r"^((\d+\.)+|\w+\.)\s*", "", path_parts[0].strip()).lower()
            for node in structure_nodes:
                node_title = re.sub(r"^((\d+\.)+|\w+\.)\s*", "", node['title'].strip()).lower()
                if node_title == target_title:
                    if len(path_parts) == 1: return node
                    if 'children' in node and node['children']:
                        return find_node_by_path(node['children'], path_parts[1:])
            return None

        for i, chunk_content in enumerate(chunks):
            logger.info(f"  Mapping chunk {i + 1}/{len(chunks)}")
            structure_titles = "\n".join([f"- {node['title']}" for node in flat_structure])
            prompt = PROMPT_MAP_CHUNK_TO_STRUCTURE.format(
                book_structure_titles=structure_titles,
                chunk_text=chunk_content
            )
            
            result = self.client.generate_content(
                prompt=prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": REWRITE_MAX_TOKENS * 2},
                response_schema=MappedContent
            )

            if not result or "mappings" not in result:
                continue

            for item in result["mappings"]:
                path_parts = item['title'].split(' > ')
                target_node = find_node_by_path(structured_book_with_content, path_parts)
                if target_node:
                    if 'raw_content' not in target_node:
                        target_node['raw_content'] = []
                    target_node['raw_content'].append(item['source_text'])

        return structured_book_with_content

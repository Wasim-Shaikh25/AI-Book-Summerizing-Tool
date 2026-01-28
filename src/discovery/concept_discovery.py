import logging
import json
import re
from typing import List, Dict, Any, Optional
from src.core.gemini.async_client import GeminiAsyncClient
from src.core.gemini.prompts.prompts import PROMPT_DISCOVER_CONCEPTS
from src.utils.async_manager import AsyncExecutionManager
from src.core.semantic.models import ConceptTermRecord

logger = logging.getLogger(__name__)

class ConceptDiscoveryAgent:
    """
    Analyzes semantic chunks to discover and extract academic concepts bottom-up.
    Outputs flat term records without any topic authority or hierarchy.
    """
    def __init__(self):
        self.client = GeminiAsyncClient(max_concurrent=10)
        self.async_manager = AsyncExecutionManager(max_concurrency=10)

    async def discover_concepts_async(self, semantic_chunk: str, trace: Optional[Any] = None, task_name: str = "discovery") -> List[ConceptTermRecord]:
        """
        Asynchronously extracts concepts from a single semantic chunk.
        """
        prompt = PROMPT_DISCOVER_CONCEPTS.format(semantic_chunk=semantic_chunk)
        response = await self.client.generate(
            prompt=prompt,
            trace=trace,
            task_name=task_name,
            generation_config={"temperature": 0.2}
        )
        return self._parse_concepts(response)

    def discover_concepts(self, semantic_chunk: str) -> List[ConceptTermRecord]:
        """
        Extracts concepts from a single semantic chunk (Synchronous wrapper).
        """
        logger.info("Discovering concepts from semantic chunk...")
        return self.async_manager.run_single(self.discover_concepts_async, args=(semantic_chunk,))

    def discover_concepts_batch(self, chunks: List[str]) -> List[List[ConceptTermRecord]]:
        """
        Extracts concepts from multiple chunks in parallel.
        """
        logger.info(f"Discovering concepts from {len(chunks)} chunks in parallel...")
        task_defs = [(self.discover_concepts_async, (chunk,), {}) for chunk in chunks]
        return self.async_manager.run_parallel(task_defs)

    def _parse_concepts(self, response: str) -> List[ConceptTermRecord]:
        """
        Parses and normalizes concepts from LLM response.
        Enforces strict flat output format.
        """
        result = []
        if not response:
            return result

        try:
            # Clean response if it contains markdown fences
            clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
            # Robust JSON parsing
            start_idx = clean_response.find('{')
            end_idx = clean_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_response = clean_response[start_idx:end_idx+1]
                
            data = json.loads(clean_response)
            raw_terms = data.get("terms", [])
            
            for term_data in raw_terms:
                classification = term_data.get("classification", "REFERENCED_ONLY")
                
                # STRICT RULE: EXPLAINED_CONCEPT only if definition/explanation is explicit
                if classification == "EXPLAINED_CONCEPT" and not term_data.get("verbatim_evidence"):
                    logger.debug(f"Skipping explained concept '{term_data.get('term')}' - missing verbatim evidence.")
                    continue

                record = ConceptTermRecord(
                    term=term_data.get("term", "Unknown"),
                    classification=classification,
                    verbatim_evidence=term_data.get("verbatim_evidence"),
                    source_location=term_data.get("source_location"),
                    confidence=float(term_data.get("confidence", 0.0))
                )
                result.append(record)
                
            return result
        except Exception as e:
            logger.error(f"Failed to parse discovered concepts: {e}")
            return result

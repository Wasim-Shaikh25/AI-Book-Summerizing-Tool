import logging
import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_DEDUPLICATE_TOPICS

logger = logging.getLogger(__name__)

class MergeGroup(BaseModel):
    primary: str = Field(..., description="The primary name for the topic group.")
    secondary: List[str] = Field(default_factory=list, description="Alternative names to be merged into the primary.")

class DeduplicationResult(BaseModel):
    merge_groups: List[MergeGroup]

class TopicDeduplicator:
    """
    Detects and merges semantically identical topics using Gemini.
    """
    def __init__(self):
        self.client = GeminiClient()

    def deduplicate(self, topics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Identifies merge groups from a list of topics.
        Input topics should have 'topic_name' and 'source_chunks'.
        """
        if not topics:
            return {"merge_groups": []}

        # Prepare a simplified list for the prompt to save tokens
        simplified_topics = [
            {"name": t.get("topic_name"), "context_snippet": " ".join(t.get("source_chunks", []))[:200]}
            for t in topics
        ]
        
        prompt = PROMPT_DEDUPLICATE_TOPICS.format(
            topics_list=json.dumps(simplified_topics, indent=2)
        )

        logger.info(f"Deduplicating {len(topics)} topics...")
        
        result = self.client.generate_content(
            prompt=prompt,
            response_schema=DeduplicationResult
        )

        if not result or "merge_groups" not in result:
            logger.warning("Deduplication returned no merge groups or invalid format.")
            return {"merge_groups": []}

        return result

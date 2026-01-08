import logging
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_MAP_TOPIC_RELATIONSHIPS

logger = logging.getLogger(__name__)

class Relationship(BaseModel):
    topic: str = Field(..., description="The related topic name.")
    relation: Literal["depends_on", "explains", "applies", "exception_to", "example_of"] = Field(..., description="The type of semantic relationship.")

class RelationshipResult(BaseModel):
    relationships: List[Relationship]

class TopicRelationshipMapper:
    """
    Identifies semantic relationships between topics using Gemini.
    """
    def __init__(self):
        self.client = GeminiClient()

    def map_relationships(self, topic_name: str, list_of_other_topics: List[str]) -> Dict[str, Any]:
        """
        Maps relationships between a target topic and a list of other topics.
        """
        if not list_of_other_topics:
            return {"relationships": []}

        prompt = PROMPT_MAP_TOPIC_RELATIONSHIPS.format(
            topic_name=topic_name,
            list_of_other_topics=", ".join(list_of_other_topics)
        )

        logger.info(f"Mapping relationships for topic '{topic_name}'...")
        
        result = self.client.generate_content(
            prompt=prompt,
            response_schema=RelationshipResult
        )

        if not result or "relationships" not in result:
            logger.warning(f"Relationship mapping failed for '{topic_name}'.")
            return {"relationships": []}

        return result

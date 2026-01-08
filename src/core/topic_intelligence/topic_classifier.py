import logging
from typing import Dict, Any, Literal
from pydantic import BaseModel, Field
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_CLASSIFY_TOPIC

logger = logging.getLogger(__name__)

class ClassificationResult(BaseModel):
    topic_type: Literal["core_concept", "sub_concept", "reference_only", "example", "application", "definition_only"] = Field(..., description="The category of the topic.")
    explanation_depth: Literal["detailed", "brief", "none"] = Field(..., description="The required depth of explanation.")
    definition_status: Literal["needs_explanation", "already_explained", "reference_only"] = Field(..., description="Whether the topic needs a full definition.")

class TopicClassifier:
    """
    Classifies topics based on importance and required explanation depth using Gemini.
    """
    def __init__(self):
        self.client = GeminiClient()

    def classify(self, topic_name: str, consolidated_text: str, frequency_count: int) -> Dict[str, Any]:
        """
        Classifies a topic based on its content and frequency.
        """
        prompt = PROMPT_CLASSIFY_TOPIC.format(
            topic_name=topic_name,
            frequency_count=frequency_count,
            consolidated_text=consolidated_text
        )

        logger.info(f"Classifying topic '{topic_name}'...")
        
        result = self.client.generate_content(
            prompt=prompt,
            response_schema=ClassificationResult
        )

        if not result:
            logger.warning(f"Classification failed for '{topic_name}'. Returning default values.")
            return {
                "topic_type": "core_concept",
                "explanation_depth": "detailed",
                "definition_status": "needs_explanation"
            }

        return result

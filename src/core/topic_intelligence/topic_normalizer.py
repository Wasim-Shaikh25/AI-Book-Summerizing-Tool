import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_NORMALIZE_TOPIC
from src.utils.cpu_manager import CPUExecutionManager

logger = logging.getLogger(__name__)

class NormalizedTopic(BaseModel):
    canonical_topic_name: str = Field(..., description="The formal, academic name for the topic.")
    alternative_names: List[str] = Field(default_factory=list, description="Synonyms or other names used in the text.")

class TopicNormalizer:
    """
    Normalizes topic names using Gemini to ensure consistency and formal naming.
    """
    def __init__(self):
        self.client = GeminiClient()
        self.cpu_manager = CPUExecutionManager()

    def normalize_text_cpu(self, text: str) -> str:
        """
        CPU-bound text normalization (lowercase, strip, remove special chars).
        """
        import re
        text = text.lower().strip()
        text = re.sub(r'[^\w\s]', '', text)
        return text

    def batch_normalize_text_cpu(self, texts: List[str]) -> List[str]:
        """
        Runs basic text normalization in parallel using the CPU pool.
        """
        return self.cpu_manager.run_parallel(self.normalize_text_cpu, texts)

    def normalize(self, raw_topic_name: str, consolidated_text: str) -> Dict[str, Any]:
        """
        Normalizes a topic name based on its content.
        Retries once on failure, then raises an exception.
        """
        prompt = PROMPT_NORMALIZE_TOPIC.format(
            raw_topic_name=raw_topic_name,
            consolidated_text=consolidated_text
        )

        for attempt in range(2):
            try:
                logger.info(f"Normalizing topic '{raw_topic_name}' (Attempt {attempt + 1})")
                result = self.client.generate_content(
                    prompt=prompt,
                    response_schema=NormalizedTopic
                )
                
                if result and "canonical_topic_name" in result:
                    return result
                
                if attempt == 0:
                    logger.warning(f"Normalization failed for '{raw_topic_name}', retrying...")
                
            except Exception as e:
                logger.error(f"Error during normalization attempt {attempt + 1}: {str(e)}")
                if attempt == 1:
                    raise Exception(f"Topic normalization failed twice for '{raw_topic_name}': {str(e)}")

        raise Exception(f"Topic normalization failed to produce valid schema for '{raw_topic_name}' after 2 attempts.")

import logging
from typing import Any, List

# Structural reset: Gemini removed.
# from src.core.gemini.client import GeminiClient
from src.interaction.command_parser import IntentResult

logger = logging.getLogger(__name__)


class ContentGenerationEngine:
    """
    Structural reset: content generation engine disabled until replacement is implemented.

    Runtime placeholder: allow the CLI to boot; real generation will be re-enabled later.
    """
    def __init__(self, client: Any = None):
        self.client = client

    def generate(self, intent: IntentResult, chunks: List[str], knowledge_gap: bool) -> str:
        """
        Generates content following strict deterministic rules.
        """
        logger.info(f"Generating content for task: {intent.task_type}")
        
        formatted_chunks = "\n---\n".join(chunks) if chunks else "No book content provided."
        
        # Centralized prompt store (even though generation is disabled, keep prompt source consistent)
        from src.LLMAdaptor.client import LLMClient

        client = LLMClient.from_config()
        prompt = client.generate(
            "content_generation",
            variables={
                "intent_json": intent.model_dump_json(),
                "knowledge_gap": "true" if knowledge_gap else "false",
                "allow_external": "true" if intent.allow_external_knowledge else "false",
                "chunks": formatted_chunks,
                "query": intent.normalized_query,
            },
        )
        # Keep variable to avoid unused warnings / future re-enable. Current engine returns placeholder below.
        _ = prompt

        # Placeholder response to keep CLI functional during stabilization.
        return (
            f"# Question: {intent.normalized_query}\n\n"
            "1. Content generation is currently disabled in this build.\n"
            "2. The rest of the pipeline (ingestion/structure) can be stabilized independently.\n"
        )

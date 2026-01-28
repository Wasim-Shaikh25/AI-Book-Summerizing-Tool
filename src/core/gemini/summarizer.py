import logging
from typing import List
from src.core.gemini.async_client import GeminiAsyncClient
from src.config import REWRITE_MAX_TOKENS
from src.core.gemini.prompts.prompts import PROMPT_REWRITE_NODE_CONTROLLED
from src.utils.async_manager import AsyncExecutionManager

logger = logging.getLogger(__name__)

class Summarizer:
    """
    Rewrites consolidated content into structured, exam-oriented notes.
    """
    def __init__(self, active_model: str = "GEMINI"):
        self.client = GeminiAsyncClient()
        self.async_manager = AsyncExecutionManager()

    async def rewrite_node_controlled_async(self, node_title: str, node_content: str, explained_concepts: List[str], heading_level: int) -> str:
        """
        Rewrites the consolidated content for a single structure node.
        """
        logger.info(f"Rewriting node: {node_title} (Level {heading_level})")

        explained_concepts_context = "- " + "\n- ".join(explained_concepts) if explained_concepts else "None yet."
        
        selected_prompt = PROMPT_REWRITE_NODE_CONTROLLED

        prompt = selected_prompt.format(
            node_title=node_title,
            node_content=node_content,
            explained_concepts_context=explained_concepts_context
        )
        
        rewritten_text = await self.client.generate(
            prompt=prompt,
            generation_config={"temperature": 0.7, "max_output_tokens": REWRITE_MAX_TOKENS * 2}
        )

        return rewritten_text.strip() if isinstance(rewritten_text, str) else ""

    def rewrite_node_controlled(self, node_title: str, node_content: str, explained_concepts: List[str], heading_level: int) -> str:
        """
        Rewrites the consolidated content for a single structure node (Synchronous wrapper).
        """
        return self.async_manager.run_single(
            self.rewrite_node_controlled_async(node_title, node_content, explained_concepts, heading_level)
        )

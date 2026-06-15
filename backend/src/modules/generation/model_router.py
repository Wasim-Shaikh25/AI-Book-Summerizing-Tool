from __future__ import annotations

from typing import Any, Dict

from src.modules.pipeline.llm_chat_client import LlmChatClient
from src.shared.llm_provider import rewrite_provider_order


class RewriteModelRouter:
    """Routes rewrite/RAG generation through LLM_PROVIDER (OpenAI or OpenRouter)."""

    def __init__(self) -> None:
        self._client = LlmChatClient.from_config()

    def generate(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 1200) -> Dict[str, Any]:
        for provider in rewrite_provider_order():
            text = self._client.chat_with_provider(
                provider,
                system=system_prompt,
                user=user_prompt,
                max_tokens=max_tokens,
            )
            if not text:
                continue
            if provider in {"openai", "openrouter"}:
                return {"provider": provider, "model": self._client.last_model_label(), "text": text}
        return {"provider": "none", "text": ""}

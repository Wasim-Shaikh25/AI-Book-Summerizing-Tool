from __future__ import annotations

from typing import Any, Dict

from src import config
from src.modules.pipeline.llm_chat_client import LlmChatClient, ensure_local_rewrite_model, normalize_chat_provider


class RewriteModelRouter:
    """
    Routes rewrite/RAG generation through LLM_PROVIDER (or REWRITE_PROVIDER_ORDER override).
    """

    def __init__(self) -> None:
        self._client = LlmChatClient.from_config()
        self._model_path = ensure_local_rewrite_model()

    def generate(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 1200) -> Dict[str, Any]:
        order = [
            normalize_chat_provider(p)
            for p in (config.REWRITE_PROVIDER_ORDER or config.LLM_PROVIDER or "llamacpp").split(",")
            if p.strip()
        ]
        for provider in order:
            text = self._client.chat_with_provider(
                provider,
                system=system_prompt,
                user=user_prompt,
                max_tokens=max_tokens,
            )
            if not text:
                continue
            if provider == "llamacpp":
                return {"provider": "llamacpp", "model_path": self._model_path, "text": text}
            if provider == "openai":
                return {"provider": "openai", "model": self._client.last_model_label(), "text": text}
            if provider == "gemini":
                return {"provider": "gemini", "model": self._client.last_model_label(), "text": text}
            if provider == "ollama":
                return {"provider": "ollama", "model": self._client.last_model_label(), "text": text}
        return {"provider": "none", "text": ""}

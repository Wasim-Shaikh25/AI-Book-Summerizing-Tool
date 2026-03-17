from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.config import ACTIVE_MODEL, BASE_DIR

from .prompt_store import PromptStore
from .providers.base import BaseLLMProvider, LLMResult
from .providers.gemini_provider import GeminiProvider
from .providers.qwen_provider import QwenProvider


def _default_prompts_dir() -> Path:
    # BASE_DIR points to project root; keep prompts in src/LLMAdaptor/prompts
    return Path(BASE_DIR) / "src" / "LLMAdaptor" / "prompts"


def _render_template(template: str, variables: dict[str, Any] | None) -> str:
    """
    Minimal prompt templating.

    - Uses Python format: "Hello {name}" with variables={"name": "..."}.
    - Escapes any literal braces in prompt files so JSON examples like
      `{ "results": [...] }` don't get treated as format placeholders.
    """
    if not variables:
        return template

    # Escape literal braces first, then unescape our placeholders.
    safe = template.replace("{", "{{").replace("}", "}}")
    for k in variables.keys():
        safe = safe.replace("{{" + k + "}}", "{" + k + "}")

    return safe.format(**variables)


@dataclass
class LLMClient:
    provider: BaseLLMProvider
    prompts: PromptStore

    @classmethod
    def from_config(cls, prompts_dir: Optional[Path] = None) -> "LLMClient":
        model = (ACTIVE_MODEL or "GEMINI").strip().upper()
        provider: BaseLLMProvider
        if model == "GEMINI":
            provider = GeminiProvider()
        elif model in ("QWEN", "LOCAL_QWEN"):
            provider = QwenProvider()
        else:
            raise ValueError(f"Unsupported ACTIVE_MODEL={ACTIVE_MODEL!r}. Supported: GEMINI, QWEN")

        store = PromptStore(prompts_dir or _default_prompts_dir())
        return cls(provider=provider, prompts=store)

    def generate(
        self,
        prompt_key: str,
        *,
        variables: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
    ) -> LLMResult:
        bundle = self.prompts.get(prompt_key)
        system = _render_template(bundle.system, variables)
        user = _render_template(bundle.user, variables)

        return self.provider.generate(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
            response_mime_type=response_mime_type,
        )

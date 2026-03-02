from __future__ import annotations

from abc import ABC, abstractmethod

import google.generativeai as genai


class AIAdapter(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class GeminiAdapter(AIAdapter):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro"):
        # google.generativeai reads the API key from genai.configure(api_key=...)
        # If api_key is empty, the SDK may fall back to ADC and raise DefaultCredentialsError.
        genai.configure(api_key=(api_key or None))
        self.model = genai.GenerativeModel(model_name)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # Lightweight trace so we can confirm Gemini is being invoked during runs.
        # Avoid relying on SDK-private helpers (API differs across versions).
        api_key_present = bool(self.model._client_config.get("api_key")) if hasattr(self.model, "_client_config") else None
        print(
            f"[GeminiAdapter] generate() model={getattr(self.model, 'model_name', None) or 'unknown'} "
            f"api_key_present={api_key_present} system_chars={len(system_prompt)} user_chars={len(user_prompt)}"
        )

        # google.generativeai (deprecated SDK) only supports roles: "user" and "model".
        # Put system instructions into the user content.
        combined_user = f"{system_prompt}\n\n{user_prompt}"

        response = self.model.generate_content(
            combined_user,
            generation_config={
                "temperature": 0,
                "top_p": 1,
            },
        )
        return response.text

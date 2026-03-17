"""
LLMAdaptor: common interface layer for all LLM providers (Gemini, Qwen, etc).

Goal:
- Remove tight coupling to any single provider across the codebase.
- Provide a unified client (LLMClient) that can be toggled via config.
- Provide a shared prompt store with a single naming convention.
"""

"""Signal-Sections rewrite layer.

One LLM call per high-signal section using OpenRouter (Gemini Flash Lite by
default). The prompt receives the full chapter/section/inner-heading ladder
so the model can decide which inner headings are real h3 sub-topics.

Modules:
    hierarchy_prompt        - build the structural-aware system + user prompts
    inner_heading_decider   - post-validate ``###`` usage in LLM output
    rewrite_engine          - parallel rewrite driver via existing LlmChatClient
"""

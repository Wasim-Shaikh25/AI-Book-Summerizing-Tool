"""Supported intent options presented to the classifier LLM."""

from __future__ import annotations

INTENT_OPTIONS: list[dict[str, str]] = [
    {
        "task_type": "rewrite_book",
        "description": "Rewrite or generate notes for the entire book from source text.",
    },
    {
        "task_type": "study_notes",
        "description": "Create study or exam-prep notes for the full book.",
    },
    {
        "task_type": "revision_notes",
        "description": "Create short last-minute revision notes for the full book.",
    },
    {
        "task_type": "summarize_book",
        "description": "Summarize the full book (shorter than full rewrite).",
    },
    {
        "task_type": "explain_section",
        "description": "Explain one section or topic only — not a full-book rewrite.",
    },
    {
        "task_type": "question_answer",
        "description": "Answer a specific question about the book.",
    },
    {
        "task_type": "export",
        "description": "Export existing notes to Word/PDF without new generation.",
    },
    {
        "task_type": "clarify",
        "description": "User request is too vague — ask a clarifying question.",
    },
]


def intent_options_for_prompt() -> str:
    """Human-readable catalog for classifier system prompt."""
    lines = ["Available intents (pick exactly one task_type):"]
    for opt in INTENT_OPTIONS:
        lines.append(f"- {opt['task_type']}: {opt['description']}")
    return "\n".join(lines)


def is_rewrite_task(task_type: str) -> bool:
    return task_type in {
        "rewrite_book",
        "summarize_book",
        "study_notes",
        "revision_notes",
    }


def is_qa_task(task_type: str) -> bool:
    return task_type in {"question_answer", "explain_section"}

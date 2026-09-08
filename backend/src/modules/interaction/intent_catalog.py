"""Supported intent options presented to the classifier LLM."""

from __future__ import annotations

INTENT_OPTIONS: list[dict[str, str]] = [
    {
        "task_type": "rewrite_book",
        "description": "Rewrite or generate notes for the entire book from source text. Works for textbooks, manuals, acts, treatises, reports.",
    },
    {
        "task_type": "study_notes",
        "description": "Create structured learning notes for the full book. Examples: study guides, exam prep, technical summaries, reference sheets.",
    },
    {
        "task_type": "revision_notes",
        "description": "Create concise quick-reference notes for the full book. Examples: last-minute revision, cheat sheets, executive summaries, key points.",
    },
    {
        "task_type": "summarize_book",
        "description": "Summarize the full book (shorter than full rewrite). Works for any domain.",
    },
    {
        "task_type": "explain_section",
        "description": "Explain one section or topic only — not a full-book rewrite. Works for any subject area.",
    },
    {
        "task_type": "question_answer",
        "description": "Answer a specific question about the book. Works for legal queries, technical questions, research inquiries, etc.",
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

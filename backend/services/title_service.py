"""Conversation title generation from user messages."""

from __future__ import annotations

import re

_PREFIXES = (
    "please",
    "can you",
    "could you",
    "rewrite",
    "explain",
    "answer",
    "create",
    "generate",
    "summarize",
    "give me",
)


def generate_conversation_title(user_message: str, book_title: str = "") -> str:
    text = user_message.strip()
    lowered = text.lower()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip(" :,-.")
            break

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return (book_title[:48] + "...") if len(book_title) > 48 else (book_title or "New chat")

    if len(text) <= 56:
        return text[0].upper() + text[1:] if text else "New chat"
    return text[:53].rstrip() + "..."

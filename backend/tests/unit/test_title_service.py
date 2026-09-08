"""Tests for conversation title generation."""

from services.title_service import generate_conversation_title


def test_title_from_question():
    title = generate_conversation_title("Explain the difference between tort and crime", "Torts")
    assert "difference" in title.lower()


def test_title_strips_prefix():
    title = generate_conversation_title("Please rewrite the book in simple English", "Book")
    assert not title.lower().startswith("please")


def test_title_fallback_to_book():
    title = generate_conversation_title("", "Law of Torts 2018")
    assert "Law of Torts" in title

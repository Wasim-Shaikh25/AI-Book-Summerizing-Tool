"""Tests for Word export policy."""

from services.export_policy import (
    is_full_rewrite_intent,
    resolve_export_mode,
    should_auto_docx_for_qa,
    user_requests_word_export,
)
from src.modules.interaction.command_parser import IntentResult


def _qa_intent(query: str = "explain negligence") -> IntentResult:
    return IntentResult(
        task_type="question_answer",
        scope="single_question",
        depth="medium",
        language_level="standard",
        format_type="paragraph",
        allow_external_knowledge=True,
        normalized_query=query,
    )


def _rewrite_intent() -> IntentResult:
    return IntentResult(
        task_type="rewrite_book",
        scope="full_book",
        depth="medium",
        language_level="standard",
        format_type="exam_oriented",
        allow_external_knowledge=False,
        normalized_query="rewrite the full book",
    )


def test_full_rewrite_always_docx():
    needs, reason = resolve_export_mode(_rewrite_intent(), answer="x" * 100, user_text="rewrite")
    assert needs is True
    assert reason == "rewrite"
    assert is_full_rewrite_intent(_rewrite_intent())


def test_short_qa_stays_in_chat():
    answer = "Short answer about torts."
    needs, reason = resolve_export_mode(_qa_intent(), answer=answer, user_text="explain tort")
    assert needs is False
    assert reason == "chat_only"


def test_long_qa_auto_docx():
    answer = "x" * 5000
    needs, reason = resolve_export_mode(_qa_intent(), answer=answer, user_text="explain everything")
    assert needs is True
    assert reason == "qa_length"
    assert should_auto_docx_for_qa(answer)


def test_user_word_request():
    needs, reason = resolve_export_mode(
        _qa_intent(),
        answer="Some answer",
        user_text="give me word file for this",
    )
    assert needs is True
    assert reason == "user_request"
    assert user_requests_word_export("please export to docx")

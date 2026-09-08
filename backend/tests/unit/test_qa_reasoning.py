"""Unit tests for multi-step CoT Q&A reasoning module."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chat(return_text: str):
    """Return a mock router whose .generate() returns {'text': return_text}."""
    chat = MagicMock()
    chat.generate.return_value = {"text": return_text}
    return chat


def _make_chunk(chunk_id: str, heading: str = "Section") -> dict:
    return {
        "chunk_id": chunk_id,
        "heading": heading,
        "text": f"Content of {heading}.",
        "section_id": chunk_id,
        "book_title": "Test Book",
        "excerpt": f"Content of {heading}.",
    }


def _make_rag(chunks_per_call: list[list[dict]]):
    """Return a mock RagService whose .retrieve() cycles through the provided lists."""
    rag = MagicMock()
    rag.retrieve.side_effect = chunks_per_call
    return rag


# ---------------------------------------------------------------------------
# decompose_question tests
# ---------------------------------------------------------------------------

def test_decompose_question_returns_list_of_strings():
    from src.modules.generation.qa_reasoning import decompose_question

    chat = _make_chat(json.dumps(["Sub Q1?", "Sub Q2?"]))
    result = decompose_question("Compare X and Y in context of Z?", chat)
    assert isinstance(result, list)
    assert all(isinstance(s, str) for s in result)
    assert len(result) == 2


def test_decompose_question_returns_original_on_json_failure():
    from src.modules.generation.qa_reasoning import decompose_question

    chat = _make_chat("not valid json at all")
    original = "What is promissory estoppel?"
    result = decompose_question(original, chat)
    assert result == [original]


def test_decompose_question_caps_at_3_sub_questions():
    from src.modules.generation.qa_reasoning import decompose_question

    five = ["Q1?", "Q2?", "Q3?", "Q4?", "Q5?"]
    chat = _make_chat(json.dumps(five))
    result = decompose_question("Complex multi-part question?", chat)
    assert len(result) == 3
    assert result == five[:3]


# ---------------------------------------------------------------------------
# retrieve_for_sub_questions tests
# ---------------------------------------------------------------------------

def test_retrieve_for_sub_questions_deduplicates_chunks():
    from src.modules.generation.qa_reasoning import retrieve_for_sub_questions

    shared = _make_chunk("chunk-A", "Shared Section")
    unique_b = _make_chunk("chunk-B", "Section B")
    rag = _make_rag([
        [shared, unique_b],     # sub-question 1
        [shared],               # sub-question 2 — same chunk-A again
    ])
    result = retrieve_for_sub_questions(["Q1?", "Q2?"], rag, book_id="book-1")
    ids = [c["chunk_id"] for c in result]
    assert ids.count("chunk-A") == 1
    assert "chunk-B" in ids


def test_retrieve_for_sub_questions_respects_top_k_per_question():
    from src.modules.generation.qa_reasoning import retrieve_for_sub_questions

    chunks_q1 = [_make_chunk("c1"), _make_chunk("c2")]
    chunks_q2 = [_make_chunk("c3"), _make_chunk("c4")]
    chunks_q3 = [_make_chunk("c5"), _make_chunk("c6")]
    rag = _make_rag([chunks_q1, chunks_q2, chunks_q3])
    result = retrieve_for_sub_questions(
        ["Q1?", "Q2?", "Q3?"], rag, book_id="book-1", top_k_per_question=2
    )
    assert len(result) <= 6


# ---------------------------------------------------------------------------
# synthesize_answer tests
# ---------------------------------------------------------------------------

def test_synthesize_answer_returns_reasoning_answer():
    from src.modules.generation.qa_reasoning import ReasoningAnswer, synthesize_answer

    payload = json.dumps({
        "reasoning": "Step 1: ...",
        "answer": "The answer is X.",
        "sources": [],
    })
    chat = _make_chat(payload)
    result = synthesize_answer(
        "What is X?", ["What defines X?"], [_make_chunk("c1")], chat
    )
    assert isinstance(result, ReasoningAnswer)
    assert result.answer == "The answer is X."
    assert result.reasoning == "Step 1: ..."


def test_synthesize_answer_includes_source_citations():
    from src.modules.generation.qa_reasoning import synthesize_answer

    context = [_make_chunk("c1", "Chapter 1"), _make_chunk("c2", "Chapter 2")]
    sources = [
        {"section_id": "c1", "heading": "Chapter 1", "excerpt": "..."},
        {"section_id": "c2", "heading": "Chapter 2", "excerpt": "..."},
    ]
    payload = json.dumps({
        "reasoning": "Because ...",
        "answer": "Final answer.",
        "sources": sources,
    })
    chat = _make_chat(payload)
    result = synthesize_answer("Question?", ["Sub Q?"], context, chat)
    assert len(result.sources) == 2


def test_synthesize_answer_handles_empty_context():
    from src.modules.generation.qa_reasoning import synthesize_answer

    payload = json.dumps({
        "reasoning": "",
        "answer": "No information found in the provided context.",
        "sources": [],
    })
    chat = _make_chat(payload)
    result = synthesize_answer("Any question?", ["Sub Q?"], [], chat)
    assert result.answer != ""
    assert result.sources == []


# ---------------------------------------------------------------------------
# BookQaEngine routing tests
# ---------------------------------------------------------------------------

def test_qa_engine_uses_multistep_when_enabled():
    from src.modules.generation.qa_engine import BookQaEngine

    engine = BookQaEngine(book_title="Test Book", book_id="b1")
    engine._answer_multistep = MagicMock(return_value={"answer": "multi", "refused": False})
    engine._answer_singleshot = MagicMock(return_value={"answer": "single", "refused": False})

    sections = [{"heading": "Intro", "text": "Some text about concepts here."}]
    # Patch src.config (the shim used by qa_engine's `from src import config as cfg`)
    with patch("src.config.QA_MULTISTEP_ENABLED", 1):
        engine.answer("Compare X and Y across six words at minimum", sections)

    engine._answer_multistep.assert_called_once()
    engine._answer_singleshot.assert_not_called()


def test_qa_engine_uses_singleshot_when_disabled():
    from src.modules.generation.qa_engine import BookQaEngine

    engine = BookQaEngine(book_title="Test Book", book_id="b1")
    engine._answer_multistep = MagicMock(return_value={"answer": "multi", "refused": False})
    engine._answer_singleshot = MagicMock(return_value={"answer": "single", "refused": False})

    sections = [{"heading": "Intro", "text": "Some text about the topic."}]
    with patch("src.config.QA_MULTISTEP_ENABLED", 0):
        engine.answer("Compare X and Y across six words at minimum", sections)

    engine._answer_singleshot.assert_called_once()
    engine._answer_multistep.assert_not_called()


def test_qa_engine_uses_singleshot_for_short_question():
    from src.modules.generation.qa_engine import BookQaEngine

    engine = BookQaEngine(book_title="Test Book", book_id="b1")
    engine._answer_multistep = MagicMock(return_value={"answer": "multi", "refused": False})
    engine._answer_singleshot = MagicMock(return_value={"answer": "single", "refused": False})

    sections = [{"heading": "Intro", "text": "Some text."}]
    with patch("src.config.QA_MULTISTEP_ENABLED", 1):
        engine.answer("What is tort law?", sections)  # 4 words

    engine._answer_singleshot.assert_called_once()
    engine._answer_multistep.assert_not_called()


def test_reasoning_answer_has_hops_count():
    from src.modules.generation.qa_reasoning import (
        ReasoningAnswer,
        decompose_question,
        retrieve_for_sub_questions,
        synthesize_answer,
    )

    chat_decompose = _make_chat(json.dumps(["Sub Q1?", "Sub Q2?"]))
    sub_qs = decompose_question("Question with enough words to trigger decomposition?", chat_decompose)

    chunks = [_make_chunk("c1"), _make_chunk("c2")]
    rag = _make_rag([chunks, chunks])
    merged = retrieve_for_sub_questions(sub_qs, rag, book_id="b1")

    chat_synth = _make_chat(json.dumps({
        "reasoning": "Step ...",
        "answer": "Answer text.",
        "sources": [],
    }))
    result = synthesize_answer("Original question?", sub_qs, merged, chat_synth)

    assert result.hops == 2
    assert result.sub_questions == sub_qs

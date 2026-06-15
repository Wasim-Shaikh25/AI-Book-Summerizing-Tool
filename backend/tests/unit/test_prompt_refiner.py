"""Tests for two-stage prompt refinement."""

from __future__ import annotations

import pytest

from src.modules.interaction.command_parser import IntentResult, effective_user_instruction
from src.modules.interaction.intent_router import apply_prompt_refinement, intent_from_llm_payload
from src.modules.interaction.prompt_refiner import RefineResult, refine_user_prompt


@pytest.fixture(autouse=True)
def _refiner_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTENT_REFINER_BACKEND", "passthrough")


def test_intent_classifier_payload_routing_only() -> None:
    payload = {
        "task_type": "study_notes",
        "scope": "full_book",
        "depth": "short",
        "language_level": "simple",
        "format_type": "paragraph",
        "allow_external_knowledge": False,
        "brief_summary": "Short exam notes in simple English",
        "target_topics": [],
        "include_diagrams": False,
    }
    intent = intent_from_llm_payload(payload, user_input="make study notes")
    assert intent.task_type == "study_notes"
    assert intent.rewrite_format == ""
    assert "exam notes" in intent.normalized_query.lower()


def test_effective_user_instruction_prefers_original() -> None:
    intent = IntentResult(
        task_type="study_notes",
        scope="full_book",
        depth="short",
        language_level="simple",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="short notes",
        original_user_input="short exam notes no bullets",
        refined_instruction="Write paragraph-style exam notes in very simple English. Use bullets only for lists.",
        routing_method="llm",
        refinement_method="openai",
    )
    assert effective_user_instruction(intent) == "short exam notes no bullets"
    assert effective_user_instruction(intent, "fallback raw") == "short exam notes no bullets"


def test_effective_user_instruction_falls_back_when_no_original() -> None:
    intent = IntentResult(
        task_type="study_notes",
        scope="full_book",
        depth="short",
        language_level="simple",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="short notes summary",
        refined_instruction="Polished summary",
        routing_method="llm",
    )
    assert effective_user_instruction(intent) == "short notes summary"


def test_apply_prompt_refinement(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_refine(user_input: str, intent: IntentResult) -> RefineResult:
        return RefineResult(
            refined_instruction=f"REFINED: {user_input}",
            rewrite_format="Use short paragraphs; bullets only for 3+ item lists.",
            method="openai",
        )

    monkeypatch.setattr(
        "src.modules.interaction.intent_router.refine_user_prompt",
        _fake_refine,
    )
    base = intent_from_llm_payload(
        {
            "task_type": "study_notes",
            "scope": "full_book",
            "depth": "short",
            "language_level": "simple",
            "format_type": "paragraph",
            "allow_external_knowledge": False,
            "brief_summary": "exam notes",
        },
        user_input="short exam notes no bullets",
    )
    out = apply_prompt_refinement(base, "short exam notes no bullets")
    assert out.refinement_method == "openai"
    assert out.refined_instruction.startswith("REFINED:")
    assert out.rewrite_format == ""


def test_refiner_passthrough_when_off() -> None:
    intent = IntentResult(
        task_type="rewrite_book",
        scope="full_book",
        depth="medium",
        language_level="standard",
        format_type="free",
        allow_external_knowledge=False,
        normalized_query="rewrite",
        routing_method="llm",
    )
    result = refine_user_prompt("keep it short", intent)
    assert result.method == "passthrough"
    assert result.refined_instruction == "keep it short"

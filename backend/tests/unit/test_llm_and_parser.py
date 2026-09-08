from src.modules.pipeline.llm_chat_client import normalize_chat_provider
from src.modules.structure.final_structuring.signal_extractor import compute_line_signals


def test_normalize_chat_provider_aliases() -> None:
    assert normalize_chat_provider("CHATGPT") == "openai"
    assert normalize_chat_provider("openrouter") == "openrouter"


def test_signal_extractor_metadata_vs_content() -> None:
    meta = compute_line_signals(text="ISBN 978-1234567890", page_number=1, is_bold=False)
    assert meta["metadata_score"] >= 3
    legal = compute_line_signals(text="AIR 2020 SC held that...", page_number=10, is_bold=False)
    assert legal["content_score"] >= 3


def test_command_parser_rewrite_intent() -> None:
    from src.modules.interaction.command_parser import CommandParser

    intent = CommandParser().parse_intent("rewrite the book in simple English")
    assert intent is not None
    assert intent.scope == "full_book"  # type: ignore[union-attr]
    assert intent.task_type == "rewrite_book"  # type: ignore[union-attr]

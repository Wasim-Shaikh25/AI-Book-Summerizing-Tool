import logging

from src.modules.interaction.command_parser import IntentResult
from src.modules.storage.topic_repository import TopicRepository

logger = logging.getLogger(__name__)

_NOT_WIRED = "Ask / Q&A intents are not wired yet (Stage 3). Ingest a PDF and use full_book flows."


class AskHandler:
    """Handles ask intents — placeholder until Stage 3."""

    def __init__(self, topic_repo: TopicRepository | None = None, client: object = None) -> None:
        self.topic_repo = topic_repo

    def handle_intent(self, intent: IntentResult) -> None:
        raise NotImplementedError(_NOT_WIRED)

    def handle(self, question: str) -> None:
        intent = IntentResult(
            task_type="question_answer",
            scope="single_question",
            depth="medium",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=False,
            normalized_query=question,
        )
        self.handle_intent(intent)

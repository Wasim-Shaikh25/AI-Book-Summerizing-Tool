import logging
from typing import List

from src.modules.interaction.command_parser import IntentResult
from src.modules.storage.topic_repository import TopicRepository

logger = logging.getLogger(__name__)

_NOT_WIRED = "Question-paper intents are not wired yet (Stage 3)."


class QuestionPaperHandler:
    """Handles question-paper intents — placeholder until Stage 3."""

    def __init__(
        self,
        rewriter: object | None = None,
        topic_repo: TopicRepository | None = None,
        client: object = None,
    ) -> None:
        self.topic_repo = topic_repo

    def handle_intent(self, intent: IntentResult) -> None:
        raise NotImplementedError(_NOT_WIRED)

    def _extract_questions_from_text(self, text: str) -> List[str]:
        raise NotImplementedError(_NOT_WIRED)

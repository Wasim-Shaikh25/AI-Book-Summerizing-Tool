import logging

# Structural reset: Gemini removed.
# from src.core.gemini.client import GeminiClient
from src.interaction.command_parser import IntentResult
from src.storage.topic_repository import TopicRepository

logger = logging.getLogger(__name__)

class AskHandler:
    """
    Handles the 'ask' command.

    Structural reset: disabled until an LLM client replacement is implemented.
    """
    def __init__(self, topic_repo: TopicRepository, client: object = None):
        raise NotImplementedError("AskHandler not yet implemented.")

    def handle_intent(self, intent: IntentResult):
        """
        Processes a question-answering intent.
        """
        # 1. Retrieve relevant chunks and detect gaps
        chunks, knowledge_gap = self.retrieval_engine.retrieve(intent)
        
        # 2. Generate structured response
        answer = self.generation_engine.generate(intent, chunks, knowledge_gap)
        
        # 3. Handle output
        self.output_manager.handle_output(answer, intent, title=f"Answer for {intent.normalized_query[:30]}")

    def handle(self, question: str):
        # Legacy support
        intent = IntentResult(
            task_type="question_answer",
            scope="single_question",
            depth="medium",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=False,
            normalized_query=question
        )
        self.handle_intent(intent)

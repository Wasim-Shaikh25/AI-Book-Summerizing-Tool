import logging
from src.storage.topic_repository import TopicRepository
from src.core.gemini.client import GeminiClient
from src.interaction.command_parser import IntentResult
from src.core.retrieval_engine import RetrievalEngine
from src.core.content_generation_engine import ContentGenerationEngine
from src.core.gemini.renderer_profiles import PROFILES
from src.export.output_manager import OutputManager
from src.config import OUTPUT_FOLDER

logger = logging.getLogger(__name__)

class AskHandler:
    """
    Handles the 'ask' command using Retrieval, Generation, and Output engines.
    """
    def __init__(self, topic_repo: TopicRepository, client: GeminiClient):
        self.retrieval_engine = RetrievalEngine(topic_repo)
        self.generation_engine = ContentGenerationEngine(client)
        self.output_manager = OutputManager(OUTPUT_FOLDER)

    def handle_intent(self, intent: IntentResult):
        """
        Processes a question-answering intent.
        """
        # 1. Retrieve relevant chunks and detect gaps (Blueprint-Aware)
        chunks, knowledge_gap = self.retrieval_engine.retrieve(intent)
        
        if knowledge_gap and not intent.allow_external_knowledge:
            print("[!] The provided material does not contain sufficient information to answer this question.")
            return

        # Select Renderer Profile
        profile = PROFILES["EXAM_NOTES_MODE"] # Default Q&A to strict exam mode

        # 2. Generate structured response (Profile-Aware)
        answer = self.generation_engine.generate(intent, chunks, knowledge_gap, profile=profile)
        
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

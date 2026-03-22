import logging
import os
from typing import List

from src.core.pipeline import SmartBookRewriterEnhanced

# Structural reset: Gemini removed.
# from src.core.gemini.client import GeminiClient
from src.interaction.command_parser import IntentResult
from src.storage.topic_repository import TopicRepository

logger = logging.getLogger(__name__)

class QuestionPaperHandler:
    """
    Handles 'question_paper' intent.

    Structural reset: disabled until an LLM client replacement is implemented.
    """
    def __init__(self, rewriter: SmartBookRewriterEnhanced, topic_repo: TopicRepository, client: object = None):
        raise NotImplementedError("QuestionPaperHandler not yet implemented.")

    def handle_intent(self, intent: IntentResult):
        """
        Processes a question paper or list of questions.
        """
        raw_input = intent.normalized_query
        questions = []

        # 1. Detect if input is a PDF path or raw text
        if raw_input.lower().endswith(".pdf") and os.path.exists(raw_input):
            print(f"Reading question paper PDF: {raw_input}...")
            try:
                # Extract text from the paper
                doc_data, _ = self.pdf_reader.read_all_pdfs() 
                full_paper_text = "\n".join([p["text"] for p in doc_data])
                questions = self._extract_questions_from_text(full_paper_text)
            except Exception as e:
                logger.error(f"Failed to read question paper PDF: {e}")
                print("Error: Could not read the question paper PDF.")
                return
        else:
            # Assume raw text is a list of questions
            if '\n' in raw_input:
                questions = [q.strip() for q in raw_input.split('\n') if q.strip()]
            elif ',' in raw_input:
                questions = [q.strip() for q in raw_input.split(',') if q.strip()]
            else:
                questions = [raw_input.strip()]

        if not questions:
            print("No questions detected to process.")
            return

        print(f"\nProcessing {len(questions)} questions from the paper in a single pass...\n")
        
        # 1. Combine all questions for a single retrieval
        combined_query = "\n".join(questions)
        temp_intent = intent.model_copy(update={"normalized_query": combined_query, "scope": "multiple_questions"})
        
        # 2. Retrieve relevant chunks for all questions
        chunks, knowledge_gap = self.retrieval_engine.retrieve(temp_intent)
        
        # 3. Generate all answers in one call
        # We update the intent to explicitly ask for all questions to be answered
        final_content = self.generation_engine.generate(temp_intent, chunks, knowledge_gap)
        
        # 4. Handle output
        self.output_manager.handle_output(
            final_content, 
            intent, 
            title="Question Paper Answers"
        )

    def _extract_questions_from_text(self, text: str) -> List[str]:
        raise NotImplementedError("Question extraction not yet implemented.")

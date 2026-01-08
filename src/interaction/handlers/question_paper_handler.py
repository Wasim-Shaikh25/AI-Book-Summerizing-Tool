import logging
import os
from typing import List
from src.core.pipeline import SmartBookRewriterEnhanced
from src.storage.topic_repository import TopicRepository
from src.core.gemini.client import GeminiClient
from src.interaction.command_parser import IntentResult
from src.core.retrieval_engine import RetrievalEngine
from src.core.content_generation_engine import ContentGenerationEngine
from src.export.output_manager import OutputManager
from src.config import OUTPUT_FOLDER
from src.utils.pdf_reader import PDFReader

logger = logging.getLogger(__name__)

class QuestionPaperHandler:
    """
    Handles 'question_paper' intent by processing multiple questions using Retrieval and Generation engines.
    """
    def __init__(self, rewriter: SmartBookRewriterEnhanced, topic_repo: TopicRepository, client: GeminiClient):
        self.rewriter = rewriter
        self.retrieval_engine = RetrievalEngine(topic_repo)
        self.generation_engine = ContentGenerationEngine(client)
        self.output_manager = OutputManager(OUTPUT_FOLDER)
        self.pdf_reader = PDFReader(pdf_folder=os.path.join(os.getcwd(), "pdfs"))
        self.client = client

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
        """
        Uses Gemini to extract a clean list of questions from raw paper text.
        """
        prompt = (
            "Extract a clean list of individual questions from the following question paper text. "
            "Return ONLY a JSON array of strings. No other text.\n\n"
            f"PAPER TEXT:\n{text}"
        )
        result = self.client.generate_content(prompt, generation_config={"temperature": 0.1})
        try:
            import json
            clean_result = result.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_result)
        except:
            logger.error("Failed to parse questions from LLM response.")
            return [text[:100]] # Fallback

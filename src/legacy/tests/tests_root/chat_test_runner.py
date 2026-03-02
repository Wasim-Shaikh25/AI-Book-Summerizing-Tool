import sys
import os
import logging

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage.knowledge_store import KnowledgeStore
from src.storage.topic_repository import TopicRepository
from src.core.gemini.client import GeminiClient

# Configure logging for the test runner
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# --- GEMINI QA PROMPT ---
PROMPT_QA = (
    "You are an academic assistant. Your task is to answer the 'USER QUESTION' using ONLY the provided 'KNOWLEDGE CONTEXT'.\n"
    "**CRITICAL RULES:**\n"
    "1. **STRICT CONTEXT:** Answer only from the provided context. Do not use outside knowledge.\n"
    "2. **NO INFORMATION:** If the answer is not found in the context, say: 'The provided material does not contain sufficient information.'\n"
    "3. **TONE:** Maintain a neutral, formal, and academic tone.\n"
    "4. **FORMATTING:** Use bullet points for clarity where appropriate.\n"
    "5. **NO HALLUCINATION:** Do not invent facts or concepts.\n\n"
    "KNOWLEDGE CONTEXT:\n{context}\n\n"
    "USER QUESTION: {question}\n"
)

class ChatTestRunner:
    """
    A script-based testing system to validate Question-Answering from stored knowledge.
    
    FUTURE USAGE:
    - This logic will be migrated to a backend service (FastAPI/Flask) to support 
      real-time chat in a web or mobile UI.
    - The retrieval logic can be enhanced with vector-based semantic search.
    """
    def __init__(self):
        self.store = KnowledgeStore()
        self.topic_repo = TopicRepository(self.store)
        self.client = GeminiClient()

    def run_test(self, question: str):
        """
        Retrieves relevant knowledge and generates an answer using Gemini.
        """
        logger.info(f"\n{'='*50}")
        logger.info(f"QUESTION: {question}")
        logger.info(f"{'='*50}\n")

        # 1. Retrieve relevant topics (Keyword match on name)
        # In a production system, this would use semantic search/embeddings.
        relevant_topics = self.topic_repo.search_topics_by_name(question.split()[-1]) # Simple heuristic for testing
        if not relevant_topics:
            # Fallback: search by first word if last word fails
            relevant_topics = self.topic_repo.search_topics_by_name(question.split()[0])

        if not relevant_topics:
            logger.warning("No relevant topics found in storage.")
            print("The provided material does not contain sufficient information.")
            return

        # 2. Assemble Context
        context_parts = []
        used_topic_names = []
        for topic in relevant_topics[:3]: # Limit to top 3 topics for safety
            used_topic_names.append(topic.canonical_topic_name)
            topic_context = f"TOPIC: {topic.canonical_topic_name}\n"
            topic_context += f"CONTENT: {topic.consolidated_text}\n"
            if topic.key_points:
                topic_context += "KEY POINTS:\n- " + "\n- ".join(topic.key_points) + "\n"
            context_parts.append(topic_context)

        full_context = "\n---\n".join(context_parts)

        # 3. Call Gemini
        prompt = PROMPT_QA.format(context=full_context, question=question)
        answer = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.2} # Low temperature for factual accuracy
        )

        # 4. Print Result
        logger.info("ANSWER:")
        print(answer)
        logger.info(f"\n{'='*50}")
        logger.info(f"TOPICS USED: {', '.join(used_topic_names)}")
        logger.info(f"{'='*50}\n")

if __name__ == "__main__":
    runner = ChatTestRunner()
    
    if len(sys.argv) > 1:
        user_question = " ".join(sys.argv[1:])
    else:
        user_question = input("Enter your question: ")
    
    runner.run_test(user_question)

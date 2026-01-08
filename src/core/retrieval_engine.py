import logging
from typing import List, Dict, Any, Tuple
from src.storage.topic_repository import TopicRepository
from src.interaction.command_parser import IntentResult

logger = logging.getLogger(__name__)

class RetrievalEngine:
    """
    A reusable engine for fetching knowledge and detecting coverage gaps.
    Does NOT generate content.
    """
    def __init__(self, topic_repo: TopicRepository):
        self.topic_repo = topic_repo

    def retrieve(self, intent: IntentResult) -> Tuple[List[str], bool]:
        """
        Fetches relevant book chunks and evaluates coverage.
        Returns: (List of raw content strings, knowledge_gap_detected)
        """
        query = intent.normalized_query
        
        # 1. Fetch relevant book chunks
        # If scope is full_book, we might want to get a representative sample or all core topics
        if intent.scope == "full_book":
            relevant_topics = self.topic_repo.get_all_topics() # Assuming this exists or we use a sample
        else:
            # Search by query or specific topics if identified
            relevant_topics = self.topic_repo.search_topics_by_name(query)
            if not relevant_topics:
                # Try splitting query for keywords
                keywords = query.split()
                for kw in keywords:
                    if len(kw) > 3:
                        relevant_topics.extend(self.topic_repo.search_topics_by_name(kw))
        
        # 2. Evaluate coverage
        knowledge_gap = False
        if not relevant_topics:
            knowledge_gap = True
            return [], knowledge_gap
        
        # Deduplicate and limit chunks
        seen_content = set()
        chunks = []
        
        # Increase limit for multi-question or complex queries
        chunk_limit = 20 if len(query) > 100 or "\n" in query else 10
        
        for t in relevant_topics:
            if t.raw_content not in seen_content:
                chunks.append(t.raw_content)
                seen_content.add(t.raw_content)
            if len(chunks) >= chunk_limit:
                break
                
        full_text = "".join(chunks)
        
        # Heuristic for partial information
        # If it's a specific question but we have very little text, mark as gap
        if intent.scope == "single_question" and len(full_text) < 300:
            knowledge_gap = True
        elif not chunks:
            knowledge_gap = True

        return chunks, knowledge_gap

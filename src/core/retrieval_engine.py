import logging
import json
import re
from typing import List, Dict, Any, Tuple
from src.storage.topic_repository import TopicRepository
from src.interaction.command_parser import IntentResult
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_MAP_QUESTION_TO_CONCEPTS

logger = logging.getLogger(__name__)

class RetrievalEngine:
    """
    A reusable engine for fetching knowledge and detecting coverage gaps.
    Does NOT generate content.
    """
    def __init__(self, topic_repo: TopicRepository):
        self.topic_repo = topic_repo
        self.client = GeminiClient()
        self.confidence_threshold = 0.6

    def retrieve(self, intent: IntentResult, book_id: str = None) -> Tuple[List[str], bool]:
        """
        Fetches relevant book chunks and evaluates coverage.
        Q&A MUST always resolve against SourceBlueprint first.
        """
        query = intent.normalized_query
        
        # 1. Fetch Blueprint Concepts (Always use canonical concepts from SourceBlueprint for retrieval)
        if book_id:
            all_concepts = self.topic_repo.get_topics_by_book(book_id)
        else:
            all_concepts = self.topic_repo.get_all_topics()
        
        # Filter for canonical concepts (SourceBlueprint ground truth)
        blueprint_concepts = [c.topic for c in all_concepts if c.topic_type == "canonical_concept"]
        
        if not blueprint_concepts:
            logger.warning("No blueprint concepts found for retrieval.")
            return [], True

        # 2. Map Question to Blueprint Concepts
        logger.info(f"Mapping question to blueprint concepts: {query}")
        mapping_prompt = PROMPT_MAP_QUESTION_TO_CONCEPTS.format(
            blueprint_concepts=", ".join(blueprint_concepts),
            user_question=query
        )
        
        mapping_response = self.client.generate_content(mapping_prompt)
        mapped_concepts = []
        knowledge_gap = False
        
        if mapping_response:
            try:
                clean_response = re.sub(r'```json\s*|\s*```', '', mapping_response).strip()
                mapping_data = json.loads(clean_response)
                
                confidence = mapping_data.get("confidence", 0.0)
                if confidence < self.confidence_threshold:
                    logger.warning(f"Low mapping confidence ({confidence}). Marking as knowledge gap.")
                    knowledge_gap = True
                    return [], knowledge_gap
                
                mapped_concepts = mapping_data.get("mapped_concept_ids", [])
            except Exception as e:
                logger.error(f"Failed to parse concept mapping: {e}")
                knowledge_gap = True
                return [], knowledge_gap

        if not mapped_concepts:
            logger.warning("No concepts mapped to question.")
            knowledge_gap = True
            return [], knowledge_gap

        # 3. Fetch relevant book chunks based on mapped concept IDs
        relevant_topics = []
        for concept_id in mapped_concepts:
            topic = self.topic_repo.get_topic_by_concept_id(concept_id, book_id=book_id if book_id else "") 
            if topic:
                relevant_topics.append(topic)
        
        # 4. Evaluate coverage
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

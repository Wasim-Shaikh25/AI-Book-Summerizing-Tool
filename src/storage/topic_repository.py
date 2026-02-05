import logging
import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from src.storage.knowledge_store import KnowledgeStore
from src.storage.schema import TopicKnowledge

logger = logging.getLogger(__name__)

class TopicRepository:
    """
    Handles persistence and retrieval of granular topic knowledge.
    
    FUTURE Q&A USAGE:
    - Primary source for retrieving 'consolidated_text' and 'key_points' 
      to build LLM prompts for answering questions.
    - Supports keyword search on 'canonical_topic_name'.
    - Enables solving question papers by matching questions to stored topics.
    """
    def __init__(self, store: KnowledgeStore):
        self.store = store

    def save_topic(self, topic: TopicKnowledge):
        """Saves or updates topic knowledge using strict write guard."""
        query = '''
            INSERT OR REPLACE INTO topics 
            (topic_id, concept_id, book_id, topic, subtopic, source_page, 
             importance_score, raw_content, topic_type, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            topic.topic_id,
            topic.concept_id,
            topic.book_id,
            topic.topic,
            topic.subtopic,
            topic.source_page,
            topic.importance_score,
            topic.raw_content,
            topic.topic_type,
            json.dumps(topic.metadata, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))
        )
        self.store.execute_write(query, params)
        logger.debug(f"Topic '{topic.topic}' saved to repository.")

    def get_topics_by_book(self, book_id: str) -> List[TopicKnowledge]:
        """Retrieves all topics for a specific book."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT topic_id, concept_id, book_id, topic, subtopic, source_page, 
                   importance_score, raw_content, topic_type, metadata 
            FROM topics WHERE book_id = ?
        ''', (book_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_topic(row) for row in rows]

    def search_topics_by_name(self, query: str) -> List[TopicKnowledge]:
        """
        Performs a keyword search on topic names.
        """
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT topic_id, concept_id, book_id, topic, subtopic, source_page, 
                   importance_score, raw_content, topic_type, metadata 
            FROM topics WHERE topic LIKE ? OR subtopic LIKE ?
        ''', (f'%{query}%', f'%{query}%'))
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_topic(row) for row in rows]

    def get_all_topics(self) -> List[TopicKnowledge]:
        """Retrieves all topics from the repository."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT topic_id, concept_id, book_id, topic, subtopic, source_page, 
                   importance_score, raw_content, topic_type, metadata 
            FROM topics
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_topic(row) for row in rows]

    def get_topic_by_concept_id(self, concept_id: str, book_id: str) -> Optional[TopicKnowledge]:
        """Retrieves a specific topic by its stable concept_id."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT topic_id, concept_id, book_id, topic, subtopic, source_page, 
                   importance_score, raw_content, topic_type, metadata 
            FROM topics WHERE concept_id = ? AND book_id = ?
        ''', (concept_id, book_id))
        row = cursor.fetchone()
        conn.close()
        
        return self._map_row_to_topic(row) if row else None

    def _map_row_to_topic(self, row: tuple) -> TopicKnowledge:
        """Maps a database row back to a TopicKnowledge object."""
        # row indices based on explicit SELECT:
        # 0:topic_id, 1:concept_id, 2:book_id, 3:topic, 4:subtopic, 5:source_page, 
        # 6:importance_score, 7:raw_content, 8:topic_type, 9:metadata
        
        metadata_raw = row[9]
        if metadata_raw is None:
            metadata = {}
        elif isinstance(metadata_raw, (str, bytes, bytearray)):
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                metadata = {}
        else:
            metadata = {}
            
        return TopicKnowledge(
            topic_id=row[0],
            concept_id=row[1],
            book_id=row[2],
            topic=row[3],
            subtopic=row[4],
            source_page=row[5],
            importance_score=row[6] if row[6] is not None else 0.0,
            raw_content=row[7] or "",
            topic_type=row[8] or "general",
            metadata=metadata
        )

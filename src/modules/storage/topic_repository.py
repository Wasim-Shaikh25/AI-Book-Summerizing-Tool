import json
import logging
import sqlite3
from typing import List

from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.schema import TopicKnowledge

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
        """Saves or updates topic knowledge."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO topics 
                (topic_id, book_id, topic, subtopic, source_page, 
                 importance_score, raw_content, topic_type, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                topic.topic_id,
                topic.book_id,
                topic.topic,
                topic.subtopic,
                topic.source_page,
                topic.importance_score,
                topic.raw_content,
                topic.topic_type,
                json.dumps(topic.metadata)
            ))
            conn.commit()
            logger.debug(f"Topic '{topic.topic}' saved to repository.")
        except sqlite3.Error as e:
            logger.error(f"Failed to save topic: {e}")
        finally:
            conn.close()

    def get_topics_by_book(self, book_id: str) -> List[TopicKnowledge]:
        """Retrieves all topics for a specific book."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM topics WHERE book_id = ?', (book_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_topic(row) for row in rows]

    def search_topics_by_name(self, query: str) -> List[TopicKnowledge]:
        """
        Performs a keyword search on topic names.
        """
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM topics WHERE topic LIKE ? OR subtopic LIKE ?', (f'%{query}%', f'%{query}%'))
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_topic(row) for row in rows]

    def get_all_topics(self) -> List[TopicKnowledge]:
        """Retrieves all topics from the repository."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM topics')
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_topic(row) for row in rows]

    def _map_row_to_topic(self, row: tuple) -> TopicKnowledge:
        """Maps a database row back to a TopicKnowledge object."""
        return TopicKnowledge(
            topic_id=row[0],
            book_id=row[1],
            topic=row[2],
            subtopic=row[3],
            source_page=row[4],
            importance_score=row[5],
            raw_content=row[6],
            topic_type=row[7],
            metadata=json.loads(row[8])
        )

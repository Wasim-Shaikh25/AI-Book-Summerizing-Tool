import sqlite3
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class KnowledgeStore:
    """
    A lightweight SQLite-based storage layer for processed book knowledge.
    
    WHY SQLITE?
    - Relational structure preserves hierarchy (Book -> Chapter -> Topic).
    - Supports complex queries (e.g., "find all core concepts in Biology").
    - Future-proof: Can be easily indexed for keyword search and integrated 
      with vector extensions for semantic retrieval.
    - Persistent and portable.
    """
    def __init__(self, db_path: str = "output/knowledge_base.db"):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """Initializes the database schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Book Metadata Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                book_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                subject TEXT,
                source_file_name TEXT,
                total_pages INTEGER,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Topic Knowledge Table
        # Primary source for retrieving context for LLM-based question answering.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                topic_id TEXT PRIMARY KEY,
                book_id TEXT,
                topic TEXT NOT NULL,
                subtopic TEXT,
                source_page INTEGER,
                importance_score REAL,
                raw_content TEXT,
                topic_type TEXT,
                metadata TEXT, -- Stored as JSON string
                FOREIGN KEY (book_id) REFERENCES books (book_id)
            )
        ''')

        # Index for keyword search
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic_name ON topics (topic)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_book_id ON topics (book_id)')

        conn.commit()
        conn.close()
        logger.info(f"KnowledgeStore initialized at {self.db_path}")

    def get_connection(self):
        """Returns a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

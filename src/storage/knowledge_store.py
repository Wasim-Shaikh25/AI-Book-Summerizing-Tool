import sqlite3
import os
import logging
import threading
import asyncio
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
        self._write_lock = threading.Lock()
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
                metadata TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Topic Knowledge Table
        # Primary source for retrieving context for LLM-based question answering.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                topic_id TEXT PRIMARY KEY,
                concept_id TEXT,
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

        # Schema Migrations (Simple column checks)
        cursor.execute("PRAGMA table_info(books)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'metadata' not in columns:
            cursor.execute('ALTER TABLE books ADD COLUMN metadata TEXT')

        cursor.execute("PRAGMA table_info(topics)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'concept_id' not in columns:
            cursor.execute('ALTER TABLE topics ADD COLUMN concept_id TEXT')

        # Index for keyword search
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic_name ON topics (topic)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_book_id ON topics (book_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_concept_id ON topics (concept_id)')

        conn.commit()
        conn.close()
        logger.info(f"KnowledgeStore initialized at {self.db_path}")

    def get_connection(self):
        """Returns a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def execute_write(self, query: str, params: tuple = ()):
        """
        Executes a write operation with strict synchronous protection.
        Prevents concurrent writes and ensures no active event loop.
        """
        # 1. Assert no active event loop (prevent async writes)
        try:
            asyncio.get_running_loop()
            raise RuntimeError("CRITICAL SAFETY VIOLATION: SQLite write attempted from an asynchronous context. Database writes must be strictly synchronous to prevent corruption.")
        except RuntimeError as e:
            if "no running event loop" not in str(e):
                raise e

        # 2. Prevent concurrent writes using a threading lock
        with self._write_lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database write failed: {e}")
                raise e
            finally:
                conn.close()

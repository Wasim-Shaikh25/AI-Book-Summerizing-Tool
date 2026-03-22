import logging
import os
import sqlite3

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

        # Final TOC headings (source of truth for hierarchy)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS final_headings (
                heading_id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                text TEXT NOT NULL,
                level INTEGER,
                parent_heading_id TEXT,
                line_id INTEGER,
                page_number INTEGER,
                confidence REAL,

                -- Hierarchy metadata (optional, but persisted for traceability)
                reason TEXT,
                signals_used TEXT, -- JSON array of strings
                hierarchy_model TEXT,
                hierarchy_latency_ms INTEGER,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books (book_id),
                FOREIGN KEY (parent_heading_id) REFERENCES final_headings (heading_id)
            )
        ''')

        # Lightweight migration: add new traceability columns if DB was created before schema extension.
        # (SQLite has no IF NOT EXISTS for ADD COLUMN across all versions, so we check pragma first.)
        existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(final_headings)").fetchall()}
        if "reason" not in existing_cols:
            cursor.execute("ALTER TABLE final_headings ADD COLUMN reason TEXT")
        if "signals_used" not in existing_cols:
            cursor.execute("ALTER TABLE final_headings ADD COLUMN signals_used TEXT")
        if "hierarchy_model" not in existing_cols:
            cursor.execute("ALTER TABLE final_headings ADD COLUMN hierarchy_model TEXT")
        if "hierarchy_latency_ms" not in existing_cols:
            cursor.execute("ALTER TABLE final_headings ADD COLUMN hierarchy_latency_ms INTEGER")

        # Fragments (source of truth for fragment_id -> fragment text)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fragments (
                fragment_id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books (book_id)
            )
        ''')

        # Relationship table (future-proof: 1 heading -> many fragments)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS heading_fragments (
                heading_id TEXT NOT NULL,
                fragment_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (heading_id, fragment_id),
                FOREIGN KEY (book_id) REFERENCES books (book_id),
                FOREIGN KEY (heading_id) REFERENCES final_headings (heading_id),
                FOREIGN KEY (fragment_id) REFERENCES fragments (fragment_id)
            )
        ''')

        # Indexes for keyword search / joins
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic_name ON topics (topic)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_book_id ON topics (book_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_final_headings_book_id ON final_headings (book_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fragments_book_id ON fragments (book_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_heading_fragments_book_id ON heading_fragments (book_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_heading_fragments_heading_id ON heading_fragments (heading_id)')

        conn.commit()
        conn.close()
        logger.info(f"KnowledgeStore initialized at {self.db_path}")

    def get_connection(self):
        """Returns a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

import logging
import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from src.storage.knowledge_store import KnowledgeStore
from src.storage.schema import BookMetadata

logger = logging.getLogger(__name__)

class BookRepository:
    """
    Handles persistence and retrieval of book-level metadata.
    
    FUTURE Q&A USAGE:
    - Used to filter knowledge by subject or specific book before 
      performing semantic search.
    - Helps in identifying the source of an answer.
    """
    def __init__(self, store: KnowledgeStore):
        self.store = store

    def save_book(self, book: BookMetadata):
        """Saves or updates book metadata using strict write guard."""
        query = '''
            INSERT OR REPLACE INTO books 
            (book_id, title, subject, source_file_name, total_pages, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        params = (
            book.book_id, 
            book.title, 
            book.subject, 
            book.source_file_name, 
            book.total_pages,
            json.dumps(book.metadata, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))
        )
        self.store.execute_write(query, params)
        logger.info(f"Book '{book.title}' saved to repository.")

    def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Retrieves book metadata by ID (Alias for get_book_by_id)."""
        return self.get_book_by_id(book_id)

    def get_book_by_id(self, book_id: str) -> Optional[BookMetadata]:
        """Retrieves book metadata by ID."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM books WHERE book_id = ?', (book_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._map_row_to_book(row)
        return None

    def list_all_books(self) -> List[BookMetadata]:
        """Lists all processed books."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM books')
        rows = cursor.fetchall()
        conn.close()
        
        return [self._map_row_to_book(row) for row in rows]

    def _map_row_to_book(self, row: tuple) -> BookMetadata:
        """Maps a database row back to a BookMetadata object."""
        metadata_raw = row[5]
        if metadata_raw is None:
            metadata = {}
        elif isinstance(metadata_raw, (str, bytes, bytearray)):
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                metadata = {}
        else:
            metadata = {}

        return BookMetadata(
            book_id=row[0],
            title=row[1],
            subject=row[2],
            source_file_name=row[3],
            total_pages=row[4],
            metadata=metadata
        )

import logging
import sqlite3
from typing import List, Optional

from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.schema import BookMetadata

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
        """Saves or updates book metadata."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO books 
                (book_id, title, subject, source_file_name, total_pages)
                VALUES (?, ?, ?, ?, ?)
            ''', (book.book_id, book.title, book.subject, book.source_file_name, book.total_pages))
            conn.commit()
            logger.info(f"Book '{book.title}' saved to repository.")
        except sqlite3.Error as e:
            logger.error(f"Failed to save book: {e}")
        finally:
            conn.close()

    def get_book_by_id(self, book_id: str) -> Optional[BookMetadata]:
        """Retrieves book metadata by ID."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM books WHERE book_id = ?', (book_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return BookMetadata(
                book_id=row[0],
                title=row[1],
                subject=row[2],
                source_file_name=row[3],
                total_pages=row[4]
            )
        return None

    def list_all_books(self) -> List[BookMetadata]:
        """Lists all processed books."""
        conn = self.store.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM books')
        rows = cursor.fetchall()
        conn.close()
        
        return [
            BookMetadata(
                book_id=row[0],
                title=row[1],
                subject=row[2],
                source_file_name=row[3],
                total_pages=row[4]
            ) for row in rows
        ]

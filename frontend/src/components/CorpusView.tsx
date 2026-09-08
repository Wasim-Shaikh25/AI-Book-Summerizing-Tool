import React, { useState, useEffect } from 'react';

interface Book {
  book_id: string;
  title: string;
  total_pages: number;
  created_at: string;
}

interface CorpusViewProps {
  user_id: string;
  onBookSelect?: (bookIds: string[]) => void;
}

export function CorpusView({ user_id, onBookSelect }: CorpusViewProps) {
  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBooks, setSelectedBooks] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadBooks();
  }, [user_id]);

  const loadBooks = async () => {
    try {
      setLoading(true);
      // Call list_documents tool via API
      const response = await fetch('/api/tools/list_documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id }),
      });
      const data = await response.json();
      setBooks(data.output?.documents || []);
    } catch (err) {
      setError('Failed to load books');
    } finally {
      setLoading(false);
    }
  };

  const toggleBook = (bookId: string) => {
    const newSelected = new Set(selectedBooks);
    if (newSelected.has(bookId)) {
      newSelected.delete(bookId);
    } else {
      newSelected.add(bookId);
    }
    setSelectedBooks(newSelected);
    onBookSelect?.(Array.from(newSelected));
  };

  if (loading) return <div className="loading">Loading corpus...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="corpus-view">
      <h2>Corpus View</h2>
      <p className="subtitle">{books.length} documents available</p>
      <div className="book-grid">
        {books.map((book) => (
          <div
            key={book.book_id}
            className={`book-card ${selectedBooks.has(book.book_id) ? 'selected' : ''}`}
            onClick={() => toggleBook(book.book_id)}
          >
            <h3>{book.title}</h3>
            <p>{book.total_pages} pages</p>
            <small>{new Date(book.created_at).toLocaleDateString()}</small>
          </div>
        ))}
      </div>
      {selectedBooks.size > 0 && (
        <div className="selection-bar">
          <p>{selectedBooks.size} books selected</p>
        </div>
      )}
    </div>
  );
}

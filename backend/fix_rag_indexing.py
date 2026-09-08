"""Script to process existing books for RAG indexing."""

from pathlib import Path
from src.modules.pipeline import run_pipeline
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.book_repository import BookRepository

# Get the book that needs processing
book_id = "f9db04ee-a0b0-4069-a0a8-b375b8b3f2d2"

store = KnowledgeStore()
conn = store.get_connection()
cur = conn.cursor()
cur.execute('SELECT book_id, title, source_file_name FROM books WHERE book_id = ?', (book_id,))
row = cur.fetchone()

if not row:
    print(f"Book {book_id} not found")
    exit(1)

book = {
    'book_id': row[0],
    'title': row[1],
    'source_file_name': row[2]
}

if not book:
    print(f"Book {book_id} not found")
    exit(1)

print(f"Processing book: {book['title']}")
print(f"File path: {book['source_file_name']}")

# Find the actual PDF file
pdf_path = "c:\\python_project\\AI Notes Creater Model\\output\\uploads\\948253bb-1f06-4552-a08c-b83e73b20f10\\law_of_tort.pdf"

if not Path(pdf_path).exists():
    print(f"PDF file not found at {pdf_path}")
    exit(1)

print(f"Found PDF at: {pdf_path}")

# Run pipeline with database persistence
print("Running pipeline with persist_to_db=True...")
result, pipeline_logger = run_pipeline(
    pdf_path,
    enable_logs=True,
    persist_to_db=True,
)

print(f"Pipeline completed. Book title: {result.book_title}")
print(f"Total pages: {result.total_pages}")
print(f"Log directory: {pipeline_logger.run_dir if pipeline_logger else None}")

# Build RAG index
from src.modules.rag.service import RagService
from src.modules.storage.knowledge_store import KnowledgeStore

store = KnowledgeStore()
conn = store.get_connection()
cur = conn.cursor()

# Get sections
cur.execute('SELECT section_id, title, content FROM sections WHERE book_id = ?', (book_id,))
sections = []
for row in cur.fetchall():
    sections.append({
        'section_id': row[0],
        'title': row[1],
        'content': row[2]
    })

print(f"Found {len(sections)} sections")

if sections:
    rag_service = RagService(store)
    print("Building RAG index...")
    index = rag_service.ensure_index(book_id=book_id, sections=sections, force_rebuild=True)
    print(f"RAG index built with {index.chunk_count} chunks")
else:
    print("No sections found to build RAG index")

conn.close()
print("Done!")

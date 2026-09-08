"""Test QA capabilities for question generation and content retrieval."""

import os
import sys
from pathlib import Path

# Add backend to path
backend_root = Path(__file__).parent
sys.path.insert(0, str(backend_root))

from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.book_repository import BookRepository
from src.modules.interaction.handlers.ask_handler import AskHandler
from src.modules.interaction.command_parser import IntentResult
from datetime import datetime

# Configuration
PDF_PATH = "src/modules/debug/pdf_files/The Constitution Of India By Jhavala.pdf"
LOG_DIR = "c:/python_project/AI Notes Creater Model/logs/run_2026-07-09_12-39-34"
USER_ID = "test_user"
OUTPUT_DIR = "c:/python_project/AI Notes Creater Model/output/qa_results"

def get_latest_book_id():
    """Get the latest book_id from the knowledge store."""
    store = KnowledgeStore()
    book_repo = BookRepository(store)
    books = book_repo.list_all_books()
    if books:
        return books[-1].book_id  # Get the latest
    return None

def save_qa_result(result, test_name):
    """Save QA result to markdown file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{test_name}_{timestamp}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        if isinstance(result, dict):
            f.write(f"# {test_name.replace('_', ' ').title()}\n\n")
            if 'answer' in result:
                f.write(result['answer'])
            else:
                f.write(str(result))
            if 'sources' in result:
                f.write(f"\n\n## Sources\n")
                for source in result['sources']:
                    f.write(f"- {source}\n")
        else:
            f.write(f"# {test_name.replace('_', ' ').title()}\n\n")
            f.write(str(result))
    
    print(f"Saved to: {filepath}")
    return filepath

def test_question_generation():
    """Test 1: Create questions covering full syllabus (10 marks questions)."""
    print("\n" + "=" * 60)
    print("TEST 1: Question Generation - Full Syllabus Coverage")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id = get_latest_book_id()
    
    if not book_id:
        print("[!] No book found. Please run the pipeline first.")
        return None
    
    print(f"Using book_id: {book_id}")
    
    # Create ask handler
    handler = AskHandler(
        store=store,
        book_id=book_id,
        book_title="The Constitution Of India By Jhavala",
        pdf_path=PDF_PATH,
        ultimate_log_dir=LOG_DIR,
        subject_hint="Constitution of India"
    )
    
    # Test question generation
    question = "Generate 10-mark questions covering the full syllabus of the Constitution of India"
    
    # Create intent
    intent = IntentResult(
        task_type="question_answer",
        scope="full_book",
        depth="detailed",
        language_level="standard",
        format_type="exam_oriented",
        allow_external_knowledge=False,
        normalized_query="Generate 10-mark questions covering the full syllabus",
        original_user_input=question,
        refined_instruction=question
    )
    
    try:
        result = handler.handle_intent(intent)
        if result:
            print("\nGenerated Questions:")
            if isinstance(result, dict):
                print(result.get('answer', str(result)))
            else:
                print(result)
            # Save result to file
            save_qa_result(result, 'question_generation')
            return result
        else:
            print("[!] Failed to generate questions")
            return None
    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_qa_document():
    """Test 2: Create question-answer document based on generated questions."""
    print("\n" + "=" * 60)
    print("TEST 2: Question-Answer Document Generation")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id = get_latest_book_id()
    
    if not book_id:
        print("[!] No book found.")
        return None
    
    handler = AskHandler(
        store=store,
        book_id=book_id,
        book_title="The Constitution Of India By Jhavala",
        pdf_path=PDF_PATH,
        ultimate_log_dir=LOG_DIR,
        subject_hint="Constitution of India"
    )
    
    # Test QA for specific questions
    question = "Answer these questions: 1) What are the salient features of the Indian Constitution? 2) Explain the federal characteristics of the Indian Constitution."
    
    intent = IntentResult(
        task_type="question_answer",
        scope="full_book",
        depth="detailed",
        language_level="standard",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="Answer questions about salient features and federal characteristics",
        original_user_input=question,
        refined_instruction=question
    )
    
    try:
        result = handler.handle_intent(intent)
        if result:
            print("\nQuestion-Answer Document:")
            if isinstance(result, dict):
                print(result.get('answer', str(result)))
            else:
                print(result)
            # Save result to file
            save_qa_result(result, 'qa_document')
            return result
        else:
            print("[!] Failed to generate QA document")
            return None
    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_topic_explanation():
    """Test 3: Ask topic explanation from PDF."""
    print("\n" + "=" * 60)
    print("TEST 3: Topic Explanation")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id = get_latest_book_id()
    
    if not book_id:
        print("[!] No book found.")
        return None
    
    handler = AskHandler(
        store=store,
        book_id=book_id,
        book_title="The Constitution Of India By Jhavala",
        pdf_path=PDF_PATH,
        ultimate_log_dir=LOG_DIR,
        subject_hint="Constitution of India"
    )
    
    # Test topic explanation
    question = "Explain the concept of federalism in the Indian Constitution"
    
    intent = IntentResult(
        task_type="explain_section",
        scope="specific_topic",
        depth="detailed",
        language_level="standard",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="Explain federalism in Indian Constitution",
        original_user_input=question,
        refined_instruction=question
    )
    
    try:
        result = handler.handle_intent(intent)
        if result:
            print("\nTopic Explanation:")
            if isinstance(result, dict):
                print(result.get('answer', str(result)))
            else:
                print(result)
            # Save result to file
            save_qa_result(result, 'topic_explanation')
            return result
        else:
            print("[!] Failed to generate topic explanation")
            return None
    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_chapter_explanation():
    """Test 4: Ask to explain 1st chapter from book."""
    print("\n" + "=" * 60)
    print("TEST 4: Chapter Explanation")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id = get_latest_book_id()
    
    if not book_id:
        print("[!] No book found.")
        return None
    
    handler = AskHandler(
        store=store,
        book_id=book_id,
        book_title="The Constitution Of India By Jhavala",
        pdf_path=PDF_PATH,
        ultimate_log_dir=LOG_DIR,
        subject_hint="Constitution of India"
    )
    
    # Test chapter explanation
    question = "Explain the first chapter of the book in detail"
    
    intent = IntentResult(
        task_type="explain_section",
        scope="specific_topic",
        depth="detailed",
        language_level="standard",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="Explain first chapter in detail",
        original_user_input=question,
        refined_instruction=question
    )
    
    try:
        result = handler.handle_intent(intent)
        if result:
            print("\nChapter Explanation:")
            if isinstance(result, dict):
                print(result.get('answer', str(result)))
            else:
                print(result)
            # Save result to file
            save_qa_result(result, 'chapter_explanation')
            return result
        else:
            print("[!] Failed to generate chapter explanation")
            return None
    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("QA CAPABILITIES TEST")
    print("=" * 60)
    
    # Run tests
    results = {}
    
    # Test 1: Question generation
    results['question_generation'] = test_question_generation()
    
    # Test 2: QA document
    results['qa_document'] = test_qa_document()
    
    # Test 3: Topic explanation
    results['topic_explanation'] = test_topic_explanation()
    
    # Test 4: Chapter explanation
    results['chapter_explanation'] = test_chapter_explanation()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    print("\nAll tests completed.")

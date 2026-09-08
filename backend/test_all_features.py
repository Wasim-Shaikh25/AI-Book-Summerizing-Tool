"""Comprehensive test script for all system features."""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_root = Path(__file__).parent
sys.path.insert(0, str(backend_root))

from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.book_repository import BookRepository
from src.modules.interaction.handlers.ask_handler import AskHandler
from src.modules.interaction.handlers.rewrite_handler import RewriteHandler
from src.modules.interaction.command_parser import IntentResult

# Configuration
PDF_PATH = r"C:\Users\Shaikh Wasim\Downloads\LAW OF TORTS, MOTOR ACCIDENT CLAIMS AND CONSUMER.pdf"
LOG_DIR = "c:/python_project/AI Notes Creater Model/logs/run_2026-07-09_13-44-16"
USER_ID = "test_user"
OUTPUT_DIR = "c:/python_project/AI Notes Creater Model/output/feature_tests"

def get_book_details():
    """Get the latest book_id and book details from the knowledge store."""
    store = KnowledgeStore()
    book_repo = BookRepository(store)
    books = book_repo.list_all_books()
    if books:
        book = books[-1]
        return book.book_id, book.title, book.title  # Use book title as subject hint
    return None, None, None

def get_latest_book_id():
    """Get the latest book_id from the knowledge store."""
    book_id, _, _ = get_book_details()
    return book_id

def save_test_result(result, test_name):
    """Save test result to markdown file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{test_name}_{timestamp}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# {test_name.replace('_', ' ').title()}\n\n")
        if isinstance(result, dict):
            if 'answer' in result:
                f.write(result['answer'])
            else:
                f.write(str(result))
            if 'sources' in result:
                f.write(f"\n\n## Sources\n")
                for source in result['sources']:
                    f.write(f"- {source}\n")
        else:
            f.write(str(result))
    
    print(f"Saved to: {filepath}")
    return filepath

def test_rewrite_modes():
    """Test different rewrite modes (study notes, revision notes, detailed analysis)."""
    print("\n" + "=" * 60)
    print("TEST: Rewrite Modes")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found. Please process PDF first.")
        return None
    
    modes = [
        ("study_notes", "Create comprehensive study notes"),
        ("revision_notes", "Create quick revision notes for exam"),
        ("detailed_analysis", "Create detailed analysis with examples")
    ]
    
    results = {}
    for mode_name, instruction in modes:
        print(f"\nTesting mode: {mode_name}")
        # Use more specific instruction based on mode
        if mode_name == "detailed_analysis":
            instruction = "Generate comprehensive questions covering the entire syllabus with detailed analysis - include at least 20 questions covering all major topics"
        handler = AskHandler(
            store=store,
            book_id=book_id,
            book_title=book_title,
            pdf_path=PDF_PATH,
            ultimate_log_dir=LOG_DIR,
            subject_hint=subject_hint
        )
        
        intent = IntentResult(
            task_type="rewrite_book" if mode_name != "detailed_analysis" else "question_answer",
            scope="full_book",
            depth="detailed" if mode_name != "revision_notes" else "short",
            language_level="standard",
            format_type="paragraph" if mode_name != "revision_notes" else "bullet",
            allow_external_knowledge=False,
            normalized_query=instruction,
            original_user_input=instruction,
            refined_instruction=instruction
        )
        
        try:
            result = handler.handle_intent(intent)
            if result:
                save_test_result(result, f'rewrite_mode_{mode_name}')
                results[mode_name] = "PASS"
                print(f"  {mode_name}: PASS")
            else:
                results[mode_name] = "FAIL"
                print(f"  {mode_name}: FAIL")
        except Exception as e:
            results[mode_name] = f"ERROR: {e}"
            print(f"  {mode_name}: ERROR - {e}")
    
    return results

def test_output_formats():
    """Test different output formats (bullet points vs paragraphs)."""
    print("\n" + "=" * 60)
    print("TEST: Output Formats")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found.")
        return None
    
    formats = [
        ("paragraph", "Explain in paragraph format"),
        ("bullet", "Explain in bullet point format"),
        ("exam_oriented", "Create exam-oriented notes")
    ]
    
    results = {}
    for format_name, instruction in formats:
        print(f"\nTesting format: {format_name}")
        handler = AskHandler(
            store=store,
            book_id=book_id,
            book_title=book_title,
            pdf_path=PDF_PATH,
            ultimate_log_dir=LOG_DIR,
            subject_hint=subject_hint
        )
        
        intent = IntentResult(
            task_type="explain_section",
            scope="specific_topic",
            depth="detailed",
            language_level="standard",
            format_type=format_name,
            allow_external_knowledge=False,
            normalized_query=instruction,
            original_user_input=instruction,
            refined_instruction=instruction
        )
        
        try:
            result = handler.handle_intent(intent)
            if result:
                save_test_result(result, f'format_{format_name}')
                results[format_name] = "PASS"
                print(f"  {format_name}: PASS")
            else:
                results[format_name] = "FAIL"
                print(f"  {format_name}: FAIL")
        except Exception as e:
            results[format_name] = f"ERROR: {e}"
            print(f"  {format_name}: ERROR - {e}")
    
    return results

def test_depth_levels():
    """Test different depth levels (short, medium, detailed)."""
    print("\n" + "=" * 60)
    print("TEST: Depth Levels")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found.")
        return None
    
    depths = [
        ("very_short", "Give a very short summary"),
        ("short", "Give a short explanation"),
        ("medium", "Give a medium detailed explanation"),
        ("detailed", "Give a detailed explanation with examples")
    ]
    
    results = {}
    for depth_name, instruction in depths:
        print(f"\nTesting depth: {depth_name}")
        handler = AskHandler(
            store=store,
            book_id=book_id,
            book_title=book_title,
            pdf_path=PDF_PATH,
            ultimate_log_dir=LOG_DIR,
            subject_hint=subject_hint
        )
        
        intent = IntentResult(
            task_type="explain_section",
            scope="specific_topic",
            depth=depth_name,
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=False,
            normalized_query=instruction,
            original_user_input=instruction,
            refined_instruction=instruction
        )
        
        try:
            result = handler.handle_intent(intent)
            if result:
                save_test_result(result, f'depth_{depth_name}')
                results[depth_name] = "PASS"
                print(f"  {depth_name}: PASS")
            else:
                results[depth_name] = "FAIL"
                print(f"  {depth_name}: FAIL")
        except Exception as e:
            results[depth_name] = f"ERROR: {e}"
            print(f"  {depth_name}: ERROR - {e}")
    
    return results

def test_language_levels():
    """Test different language levels (simple, standard, advanced)."""
    print("\n" + "=" * 60)
    print("TEST: Language Levels")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found.")
        return None
    
    levels = [
        ("simple", "Explain in simple language for beginners"),
        ("standard", "Explain in standard language"),
        ("advanced", "Explain in advanced language with technical details")
    ]
    
    results = {}
    for level_name, instruction in levels:
        print(f"\nTesting language level: {level_name}")
        handler = AskHandler(
            store=store,
            book_id=book_id,
            book_title=book_title,
            pdf_path=PDF_PATH,
            ultimate_log_dir=LOG_DIR,
            subject_hint=subject_hint
        )
        
        intent = IntentResult(
            task_type="explain_section",
            scope="specific_topic",
            depth="detailed",
            language_level=level_name,
            format_type="paragraph",
            allow_external_knowledge=False,
            normalized_query=instruction,
            original_user_input=instruction,
            refined_instruction=instruction
        )
        
        try:
            result = handler.handle_intent(intent)
            if result:
                save_test_result(result, f'language_{level_name}')
                results[level_name] = "PASS"
                print(f"  {level_name}: PASS")
            else:
                results[level_name] = "FAIL"
                print(f"  {level_name}: FAIL")
        except Exception as e:
            results[level_name] = f"ERROR: {e}"
            print(f"  {level_name}: ERROR - {e}")
    
    return results

def test_scopes():
    """Test different scoping (full book, specific topic, single question)."""
    print("\n" + "=" * 60)
    print("TEST: Scoping")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found.")
        return None
    
    scopes = [
        ("full_book", "Cover the entire book"),
        ("specific_topic", "Focus on a specific topic"),
        ("single_question", "Answer a single specific question")
    ]
    
    results = {}
    for scope_name, instruction in scopes:
        print(f"\nTesting scope: {scope_name}")
        handler = AskHandler(
            store=store,
            book_id=book_id,
            book_title=book_title,
            pdf_path=PDF_PATH,
            ultimate_log_dir=LOG_DIR,
            subject_hint=subject_hint
        )
        
        intent = IntentResult(
            task_type="question_answer" if scope_name == "single_question" else "explain_section",
            scope=scope_name,
            depth="detailed",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=False,
            normalized_query=instruction,
            original_user_input=instruction,
            refined_instruction=instruction
        )
        
        try:
            result = handler.handle_intent(intent)
            if result:
                save_test_result(result, f'scope_{scope_name}')
                results[scope_name] = "PASS"
                print(f"  {scope_name}: PASS")
            else:
                results[scope_name] = "FAIL"
                print(f"  {scope_name}: FAIL")
        except Exception as e:
            results[scope_name] = f"ERROR: {e}"
            print(f"  {scope_name}: ERROR - {e}")
    
    return results

def test_diagrams():
    """Test diagram generation capabilities."""
    print("\n" + "=" * 60)
    print("TEST: Diagram Generation")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found.")
        return None
    
    handler = AskHandler(
        store=store,
        book_id=book_id,
        book_title=book_title,
        pdf_path=PDF_PATH,
        ultimate_log_dir=LOG_DIR,
        subject_hint=subject_hint
    )
    
    intent = IntentResult(
        task_type="explain_section",
        scope="specific_topic",
        depth="detailed",
        language_level="standard",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="Explain with diagrams",
        original_user_input="Explain the main concepts with diagrams and flowcharts",
        refined_instruction="Explain the main concepts with diagrams and flowcharts",
        include_diagrams=True
    )
    
    try:
        result = handler.handle_intent(intent)
        if result:
            save_test_result(result, 'diagram_generation')
            print("Diagram generation: PASS")
            return {"diagram_generation": "PASS"}
        else:
            print("Diagram generation: FAIL")
            return {"diagram_generation": "FAIL"}
    except Exception as e:
        print(f"Diagram generation: ERROR - {e}")
        return {"diagram_generation": f"ERROR: {e}"}

def test_citations():
    """Test citation features."""
    print("\n" + "=" * 60)
    print("TEST: Citation Features")
    print("=" * 60)
    
    store = KnowledgeStore()
    book_id, book_title, subject_hint = get_book_details()
    if not book_id:
        print("[!] No book found.")
        return None
    
    handler = AskHandler(
        store=store,
        book_id=book_id,
        book_title=book_title,
        pdf_path=PDF_PATH,
        ultimate_log_dir=LOG_DIR,
        subject_hint=subject_hint
    )
    
    intent = IntentResult(
        task_type="question_answer",
        scope="specific_topic",
        depth="detailed",
        language_level="standard",
        format_type="paragraph",
        allow_external_knowledge=False,
        normalized_query="Explain with citations",
        original_user_input="Explain the main concepts with proper citations",
        refined_instruction="Explain the main concepts with proper citations"
    )
    
    try:
        result = handler.handle_intent(intent)
        if result:
            save_test_result(result, 'citation_features')
            # Check if sources are included
            has_sources = isinstance(result, dict) and 'sources' in result and result['sources']
            if has_sources:
                print("Citation features: PASS (sources included)")
                return {"citation_features": "PASS"}
            else:
                print("Citation features: PARTIAL (answer generated but no sources)")
                return {"citation_features": "PARTIAL"}
        else:
            print("Citation features: FAIL")
            return {"citation_features": "FAIL"}
    except Exception as e:
        print(f"Citation features: ERROR - {e}")
        return {"citation_features": f"ERROR: {e}"}

def run_all_tests():
    """Run all feature tests."""
    print("=" * 60)
    print("COMPREHENSIVE FEATURE TESTS")
    print("=" * 60)
    print(f"PDF Path: {PDF_PATH}")
    print(f"Output Directory: {OUTPUT_DIR}")
    
    if not PDF_PATH:
        print("\n[!] Please provide PDF path in the script configuration.")
        return
    
    all_results = {}
    
    # Test 1: Rewrite Modes
    all_results['rewrite_modes'] = test_rewrite_modes()
    
    # Test 2: Output Formats
    all_results['output_formats'] = test_output_formats()
    
    # Test 3: Depth Levels
    all_results['depth_levels'] = test_depth_levels()
    
    # Test 4: Language Levels
    all_results['language_levels'] = test_language_levels()
    
    # Test 5: Scopes
    all_results['scopes'] = test_scopes()
    
    # Test 6: Diagram Generation
    all_results['diagrams'] = test_diagrams()
    
    # Test 7: Citation Features
    all_results['citations'] = test_citations()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for category, results in all_results.items():
        print(f"\n{category.upper()}:")
        for test_name, status in results.items():
            print(f"  {test_name}: {status}")
    
    # Save summary
    summary_path = os.path.join(OUTPUT_DIR, f"test_summary_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt")
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("COMPREHENSIVE FEATURE TEST SUMMARY\n")
        f.write("=" * 60 + "\n\n")
        for category, results in all_results.items():
            f.write(f"{category.upper()}:\n")
            for test_name, status in results.items():
                f.write(f"  {test_name}: {status}\n")
            f.write("\n")
    
    print(f"\nSummary saved to: {summary_path}")
    print("\nAll tests completed!")

if __name__ == "__main__":
    run_all_tests()

import logging

from src.core.pipeline import SmartBookRewriterEnhanced

# Structural reset: Gemini removed.
# from src.core.gemini.client import GeminiClient
from src.export.word_exporter import WordExporter
from src.interaction.command_parser import IntentResult
from src.storage.topic_repository import TopicRepository

logger = logging.getLogger(__name__)

class ExportHandler:
    """
    Handles 'export' intent.

    Structural reset: disabled until an LLM client replacement is implemented.
    """
    def __init__(self, rewriter: SmartBookRewriterEnhanced, topic_repo: TopicRepository, client: object = None, exporter: WordExporter = None):
        raise NotImplementedError("ExportHandler not yet implemented.")

    def handle_intent(self, intent: IntentResult):
        """
        Processes an export intent.
        """
        if intent.scope == "full_book":
            self.handle_export_book()
        elif intent.scope in ["selected_topics", "single_question", "multiple_questions"]:
            self.handle_export_items(intent)
        else:
            print("Could not determine the scope for export.")

    def handle_export_book(self):
        print("\nGenerating full-book summary and exporting to Word...\n")
        # Create a default intent for full book rewrite if not provided
        from src.interaction.command_parser import IntentResult
        intent = IntentResult(
            task_type="rewrite_book",
            scope="full_book",
            depth="medium",
            language_level="standard",
            format_type="exam_oriented",
            allow_external_knowledge=False,
            normalized_query="rewrite book"
        )
        results = self.rewriter.run(intent=intent, export_to_word=True)
        
        if "error" in results:
            print(f"Error: {results['error']}")
        else:
            self.output_manager.format_for_terminal(results['markdown'], title=f"Full Book Export: {self.rewriter.book_title}")
            print(f"SUCCESS! Word file exported to: {results.get('docx', 'output folder')}")

    def handle_export_items(self, intent: IntentResult):
        query_input = intent.normalized_query
        if not query_input:
            print("Please provide items for export.")
            return

        # Split by common delimiters if it looks like multiple items
        if '\n' in query_input:
            items = [q.strip() for q in query_input.split('\n') if q.strip()]
        elif ',' in query_input:
            items = [q.strip() for q in query_input.split(',') if q.strip()]
        else:
            items = [query_input.strip()]

        print(f"\nGenerating answers for {len(items)} items and exporting to Word...\n")
        
        all_results = []
        for item in items:
            print(f"Processing: {item}")
            
            # 1. Retrieve relevant chunks
            temp_intent = intent.model_copy(update={"normalized_query": item, "scope": "single_question"})
            chunks, knowledge_gap = self.retrieval_engine.retrieve(temp_intent)
            
            # 2. Generate content
            answer = self.generation_engine.generate(temp_intent, chunks, knowledge_gap)
            all_results.append(f"# {item}\n\n{answer}\n\n")

        final_content = "".join(all_results)
        
        # 3. Handle output
        self.output_manager.handle_output(
            final_content, 
            intent, 
            title=f"Exported Content: {items[0][:20]}..."
        )

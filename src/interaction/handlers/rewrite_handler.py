import logging

from src.core.retrieval_engine import RetrievalEngine

from src.config import OUTPUT_FOLDER
from src.core.content_generation_engine import ContentGenerationEngine
from src.core.pipeline import SmartBookRewriterEnhanced
from src.export.output_manager import OutputManager
from src.interaction.command_parser import IntentResult

logger = logging.getLogger(__name__)

class RewriteHandler:
    """
    Handles the 'rewrite' command using Retrieval, Generation, and Output engines.
    """
    def __init__(self, rewriter: SmartBookRewriterEnhanced):
        self.rewriter = rewriter
        self.retrieval_engine = RetrievalEngine(rewriter.topic_repo)
        self.generation_engine = ContentGenerationEngine(rewriter.summarizer.client)
        self.output_manager = OutputManager(OUTPUT_FOLDER)

    def handle_intent(self, intent: IntentResult):
        """
        Processes a rewrite intent.
        """
        if intent.scope == "full_book":
            print(f"\nGenerating full-book {intent.task_type}...\n")
            results = self.rewriter.run(
                intent=intent,
                export_to_word=(intent.format_type == "exam_oriented") # Heuristic for word export
            )
            
            if "error" in results:
                print(f"Error: {results['error']}")
            else:
                self.output_manager.format_for_terminal(results['markdown'], title=f"Full Book: {self.rewriter.book_title}")
                if intent.format_type == "exam_oriented" or "docx" in results:
                    print(f"SUCCESS: Full book exported to {results.get('docx', 'output folder')}")
                    
        elif intent.scope == "selected_topics" and intent.target_topics:
            all_rewritten = []
            for topic_name in intent.target_topics:
                print(f"\nRewriting topic: {topic_name}...\n")
                # Create a temporary intent for retrieval
                temp_intent = intent.model_copy(update={"normalized_query": topic_name})
                chunks, knowledge_gap = self.retrieval_engine.retrieve(temp_intent)
                
                if not chunks:
                    print(f"No information found for topic: {topic_name}")
                    continue
                
                rewritten = self.generation_engine.generate(intent, chunks, knowledge_gap)
                all_rewritten.append(rewritten)
            
            if all_rewritten:
                combined_content = "\n\n".join(all_rewritten)
                self.output_manager.handle_output(
                    combined_content, 
                    intent, 
                    title=f"Rewritten Topics: {', '.join(intent.target_topics[:3])}"
                )
        else:
            print("Could not determine the scope for rewriting.")

    def handle(self, argument: str = "book"):
        # Legacy support
        intent = IntentResult(
            task_type="rewrite_book",
            scope="full_book" if argument == "book" else "specific_topic",
            depth="medium",
            language_level="standard",
            format_type="paragraph",
            allow_external_knowledge=False,
            normalized_query=f"rewrite {argument}"
        )
        self.handle_intent(intent)

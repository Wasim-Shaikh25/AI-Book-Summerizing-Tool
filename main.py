import os
import time
import logging
import re
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.config import PDF_FOLDER, OUTPUT_FOLDER, CHUNK_SIZE_WORDS, ACTIVE_MODEL
from src.utils.pdf_reader import PDFReader

# Debugging: Print the active model to verify its value
print(f"DEBUG: ACTIVE_MODEL from config: {ACTIVE_MODEL}")
logger.info(f"Configured ACTIVE_MODEL: {ACTIVE_MODEL}")

if ACTIVE_MODEL == "GEMINI":
    from src.core.gemini.chunker import Chunker
    from src.core.gemini.embedder import Embedder as GeminiEmbedder
    from src.core.gemini.summarizer import Summarizer as GeminiSummarizer
    from src.core.gemini.structure_extractor import StructureExtractor as GeminiStructureExtractor
    from src.core.gemini.content_mapper import ContentMapper as GeminiContentMapper
    from src.core.gemini.concept_consolidator import ConceptConsolidator as GeminiConceptConsolidator
elif ACTIVE_MODEL == "GROK":
    from src.core.grok.chunker import Chunker
    from src.core.grok.embedder import Embedder as GrokEmbedder
    from src.core.grok.summarizer import Summarizer as GrokSummarizer
elif ACTIVE_MODEL == "OPENAI":
    from src.core.openai.chunker import Chunker
    from src.core.openai.embedder import Embedder as OpenAIEmbedder
    from src.core.openai.summarizer import Summarizer as OpenAISummarizer
else:
    raise ValueError(f"Unsupported ACTIVE_MODEL: {ACTIVE_MODEL}")
from src.export.word_exporter import WordExporter


class SmartBookRewriterEnhanced:
    """
    A comprehensive pipeline for rewriting PDF book content into structured,
    exam-oriented notes, following a 4-phase architecture to eliminate repetition
    and ensure logical flow.
    """

    def __init__(self, pdf_folder: str = PDF_FOLDER, output_folder: str = OUTPUT_FOLDER):
        self.pdf_folder = pdf_folder
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)
        self.book_title = "Rewritten Book Notes" # Default title

        self.pdf_reader = PDFReader(pdf_folder=self.pdf_folder)
        self.chunker = Chunker(chunk_size_words=CHUNK_SIZE_WORDS)
        
        if ACTIVE_MODEL == "GEMINI":
            self.embedder = GeminiEmbedder(output_folder=self.output_folder) # Still needed for potential future use or if summarizer internally uses it
            self.summarizer = GeminiSummarizer(active_model=ACTIVE_MODEL)
            self.structure_extractor = GeminiStructureExtractor(active_model=ACTIVE_MODEL)
            self.content_mapper = GeminiContentMapper(active_model=ACTIVE_MODEL)
            self.concept_consolidator = GeminiConceptConsolidator(active_model=ACTIVE_MODEL)
        elif ACTIVE_MODEL == "GROK":
            self.embedder = GrokEmbedder(output_folder=self.output_folder)
            self.summarizer = GrokSummarizer(active_model=ACTIVE_MODEL)
            # Add Grok specific structure_extractor, content_mapper, concept_consolidator if needed
        elif ACTIVE_MODEL == "OPENAI":
            self.embedder = OpenAIEmbedder(output_folder=self.output_folder)
            self.summarizer = OpenAISummarizer(active_model=ACTIVE_MODEL)
            # Add OpenAI specific structure_extractor, content_mapper, concept_consolidator if needed
        else:
            raise ValueError(f"Unsupported ACTIVE_MODEL for Embedder/Summarizer initialization: {ACTIVE_MODEL}")
            
        self.word_exporter = WordExporter(output_folder=self.output_folder)

    # ---------- Main run pipeline ----------
    def run(self) -> Dict[str, str]:
        """
        Executes the book rewriting pipeline through 4 distinct phases:
        1. Book Structure Extraction
        2. Content Mapping
        3. Concept Consolidation
        4. Controlled Rewriting
        """
        start = time.time()
        
        try:
            full_text, self.book_title = self.pdf_reader.read_all_pdfs()
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Pipeline failed at PDF reading stage: {e}")
            return {"error": str(e)}

        # Phase 1: Book Structure Extraction
        logger.info("Phase 1: Extracting book structure...")
        book_structure = self.structure_extractor.extract_structure(full_text)
        if not book_structure:
            logger.error("Pipeline failed: Could not extract book structure.")
            return {"error": "Could not extract book structure."}
        logger.info(f"Extracted {len(book_structure)} top-level nodes in the book structure.")

        # Phase 2: Content Mapping
        logger.info("Phase 2: Mapping content chunks to structure nodes...")
        chunks = self.chunker.chunk_text(full_text)
        if not chunks:
            logger.error("Pipeline failed: No chunks were generated from the PDF text.")
            return {"error": "No chunks generated."}
        
        structured_book_with_raw_content = self.content_mapper.map_chunks_to_structure(chunks, book_structure)
        if not structured_book_with_raw_content:
            logger.error("Pipeline failed: Content mapping returned empty structure.")
            return {"error": "Content mapping failed."}
        logger.info("Finished mapping content chunks.")

        # Phase 3: Concept Consolidation
        logger.info("Phase 3: Consolidating concepts within each structure node...")
        # This will be a recursive function to traverse the structure and consolidate
        def _recursively_consolidate(nodes: List[Dict[str, Any]]):
            for node in nodes:
                if 'raw_content' in node and node['raw_content']:
                    node['consolidated_content'] = self.concept_consolidator.consolidate_node_content(node['raw_content'])
                else:
                    node['consolidated_content'] = "" # Ensure it exists even if no raw content
                if 'children' in node and node['children']:
                    _recursively_consolidate(node['children'])
        
        _recursively_consolidate(structured_book_with_raw_content)
        logger.info("Finished consolidating concepts.")

        # Phase 4: Controlled Rewriting
        logger.info("Phase 4: Controlled rewriting of notes, node by node...")
        final_notes_markdown_parts: List[str] = []
        explained_concepts: List[str] = [] # To track concepts already explained

        def _recursively_rewrite(nodes: List[Dict[str, Any]], level: int = 1):
            for node in nodes:
                node_title = node['title']
                node_content = node.get('consolidated_content', '')
                
                # Determine Markdown heading level
                markdown_heading_prefix = "#" * level

                if node_content.strip(): # Only rewrite if there is actual content
                    rewritten_node_text = self.summarizer.rewrite_node_controlled(
                        node_title=node_title,
                        node_content=node_content,
                        explained_concepts=explained_concepts,
                        heading_level=level
                    )
                    # Ensure rewritten_node_text is clean and add a newline if content exists
                    cleaned_rewritten_text = rewritten_node_text.strip()
                    
                    if cleaned_rewritten_text: # Only add if rewriting produced content
                        # Ensure no leading/trailing newlines in the content itself
                        content_to_add = cleaned_rewritten_text.strip('\n')
                        final_notes_markdown_parts.append(f"{markdown_heading_prefix} {node_title}\n\n{content_to_add}\n\n")
                        explained_concepts.append(node_title)
                    else:
                        logger.warning(f"Skipping empty rewritten content for node: {node_title}. Adding heading only.")
                        final_notes_markdown_parts.append(f"{markdown_heading_prefix} {node_title}\n\n")
                        explained_concepts.append(node_title)
                else:
                    logger.info(f"Skipping rewriting for node '{node_title}' due to empty consolidated content. Adding heading only.")
                    final_notes_markdown_parts.append(f"{markdown_heading_prefix} {node_title}\n\n")
                    explained_concepts.append(node_title)

                if 'children' in node and node['children']:
                    _recursively_rewrite(node['children'], level + 1)

        _recursively_rewrite(structured_book_with_raw_content)
        
        if not final_notes_markdown_parts:
            logger.error("No final notes were generated.")
            return {"error": "No final notes generated."}

        # Join parts with a consistent separator. The individual parts now handle their own spacing.
        # The prompt is now responsible for correct newline handling within the content.
        final_document_content = "".join(final_notes_markdown_parts).strip()
        book_data = self.word_exporter.assemble_full_book_structured_text([final_document_content], self.book_title)

        raw_text_path = self.word_exporter._save_text_file(final_document_content, "rewritten_book_raw.txt")
        logger.info(f"Saved raw structured text: {raw_text_path}")

        word_path = self.word_exporter.structured_text_to_word(book_data, f"{self.book_title}.docx", toc_depth=2)
        logger.info(f"Saved Word: {word_path}")

        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed/60:.2f} minutes.")
        return {"docx": word_path}

# ----------------- Run example -----------------
if __name__ == "__main__":
    rewriter = SmartBookRewriterEnhanced(pdf_folder=PDF_FOLDER, output_folder=OUTPUT_FOLDER)
    outputs = rewriter.run()
    logger.info(f"Outputs: {outputs}")

import os
import time
import logging
import re
import json
from typing import Dict, List, Any

from src.config import PDF_FOLDER, OUTPUT_FOLDER, CHUNK_SIZE_WORDS, ACTIVE_MODEL
from src.utils.pdf_reader import PDFReader
from src.export.word_exporter import WordExporter
from src.storage.knowledge_store import KnowledgeStore
from src.storage.book_repository import BookRepository
from src.storage.topic_repository import TopicRepository
from src.storage.schema import BookMetadata, TopicKnowledge

logger = logging.getLogger(__name__)

if ACTIVE_MODEL == "GEMINI":
    from src.core.gemini.chunker import Chunker
    from src.core.gemini.summarizer import Summarizer as GeminiSummarizer
    from src.core.gemini.structure_extractor import StructureExtractor as GeminiStructureExtractor
    from src.core.gemini.content_mapper import ContentMapper as GeminiContentMapper
    from src.core.gemini.concept_consolidator import ConceptConsolidator as GeminiConceptConsolidator
    from src.core.gemini.academic_note_writer import AcademicNoteWriter as GeminiAcademicNoteWriter
else:
    # Fallbacks or other models could be imported here
    pass

class SmartBookRewriterEnhanced:
    """
    A comprehensive pipeline for rewriting PDF book content into structured,
    exam-oriented notes.
    """

    def __init__(self, pdf_folder: str = PDF_FOLDER, output_folder: str = OUTPUT_FOLDER):
        self.pdf_folder = pdf_folder
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)
        self.book_title = "Rewritten Book Notes"
        self.structured_book = None # Cache for ingested structure and content

        self.pdf_reader = PDFReader(pdf_folder=self.pdf_folder)
        self.chunker = Chunker(chunk_size_words=CHUNK_SIZE_WORDS)
        
        if ACTIVE_MODEL == "GEMINI":
            self.summarizer = GeminiSummarizer()
            self.structure_extractor = GeminiStructureExtractor()
            self.content_mapper = GeminiContentMapper()
            self.concept_consolidator = GeminiConceptConsolidator()
            self.academic_writer = GeminiAcademicNoteWriter()
        else:
            raise ValueError(f"Unsupported ACTIVE_MODEL: {ACTIVE_MODEL}")
            
        self.word_exporter = WordExporter(output_folder=self.output_folder)
        
        # Storage Layer
        self.store = KnowledgeStore()
        self.book_repo = BookRepository(self.store)
        self.topic_repo = TopicRepository(self.store)

    def ingest(self, specific_file: str = None):
        """
        Ingests PDFs, performs topic intelligence, and stores in database.
        """
        logger.info("Starting ingestion process...")
        try:
            pages_data, self.book_title = self.pdf_reader.read_all_pdfs(specific_file=specific_file)
        except Exception as e:
            logger.error(f"Ingestion failed at PDF reading stage: {e}")
            return

        # Save Book Metadata
        book_meta = BookMetadata(
            title=self.book_title,
            source_file_name=self.book_title,
            total_pages=len(pages_data)
        )
        self.book_repo.save_book(book_meta)

        # Phase 1: Structure Extraction
        # Use first 15 pages for structure extraction (TOC focus)
        structure_text = "\n\n".join([p["text"] for p in pages_data[:15]])
        full_text = "\n\n".join([p["text"] for p in pages_data])
        
        logger.info("Phase 1: Extracting book structure...")
        book_structure = self.structure_extractor.extract_structure(structure_text)
        if not book_structure:
            book_structure = self.structure_extractor.extract_structure(full_text[:50000])
            
        if not book_structure:
            logger.error("Could not extract book structure.")
            return

        # Phase 2: Content Mapping (Page by Page)
        logger.info("Phase 2: Mapping content to structure...")
        # Initialize the in-memory version
        self.structured_book = json.loads(json.dumps(book_structure))
        
        for page in pages_data:
            logger.info(f"  Processing page {page['page_number']}...")
            # Map this page's text and update self.structured_book in-place
            self.structured_book = self.content_mapper.map_chunks_to_structure([page["text"]], self.structured_book)
            # Store in DB
            self._store_mapped_page(self.structured_book, book_meta.book_id, page["page_number"])

        logger.info("Ingestion complete.")

    def _store_mapped_page(self, nodes: List[Dict[str, Any]], book_id: str, page_number: int, parent_topic: str = None):
        for node in nodes:
            if 'raw_content' in node and node['raw_content']:
                # Store each piece of content found on this page for this topic
                for content in node['raw_content']:
                    topic_knowledge = TopicKnowledge(
                        book_id=book_id,
                        topic=node['title'],
                        subtopic=parent_topic,
                        source_page=page_number,
                        importance_score=0.8 if parent_topic is None else 0.5, # Simple heuristic
                        raw_content=content,
                        topic_type="core_concept" if parent_topic is None else "sub_concept"
                    )
                    self.topic_repo.save_topic(topic_knowledge)
            
            if 'children' in node and node['children']:
                self._store_mapped_page(node['children'], book_id, page_number, node['title'])

    def run(self, intent: Any = None, export_to_word: bool = True, specific_file: str = None) -> Dict[str, str]:
        """
        Executes the 4-phase book rewriting pipeline.
        """
        from src.interaction.command_parser import IntentResult
        
        if intent is None:
            intent = IntentResult(
                task_type="rewrite_book",
                scope="full_book",
                depth="medium",
                language_level="standard",
                format_type="paragraph",
                allow_external_knowledge=False,
                normalized_query="rewrite book"
            )

        start = time.time()
        
        # Check if we already have the structured book in memory
        if self.structured_book:
            logger.info("Using existing structured book from memory. Skipping Phase 1 and 2.")
            structured_book = self.structured_book
        else:
            try:
                pages_data, self.book_title = self.pdf_reader.read_all_pdfs(specific_file=specific_file)
                # Use only first 15 pages for structure extraction to avoid context limits and get TOC
                structure_text = "\n\n".join([p["text"] for p in pages_data[:15]])
                full_text = "\n\n".join([p["text"] for p in pages_data])
            except Exception as e:
                logger.error(f"Pipeline failed at PDF reading stage: {e}")
                return {"error": str(e)}

            # Phase 1: Structure Extraction
            logger.info("Phase 1: Extracting book structure...")
            book_structure = self.structure_extractor.extract_structure(structure_text)
            if not book_structure:
                # Fallback: try with full text if first 15 pages failed
                book_structure = self.structure_extractor.extract_structure(full_text[:50000])
                
            if not book_structure:
                return {"error": "Could not extract book structure."}

            # Phase 2: Content Mapping
            logger.info("Phase 2: Mapping content chunks...")
            chunks = self.chunker.chunk_text(full_text)
            structured_book = self.content_mapper.map_chunks_to_structure(chunks, book_structure)
            self.structured_book = structured_book

        # Phase 3: Concept Consolidation
        logger.info("Phase 3: Consolidating concepts...")
        self._recursively_consolidate(structured_book)

        # Phase 4: Controlled Rewriting
        logger.info("Phase 4: Controlled rewriting...")
        final_notes_parts: List[str] = []
        explained_concepts: List[str] = []
        self._recursively_rewrite(structured_book, final_notes_parts, explained_concepts, intent=intent)
        
        if not final_notes_parts:
            return {"error": "No final notes generated."}

        final_content = "".join(final_notes_parts).strip()
        
        result = {"markdown": final_content}
        
        if export_to_word:
            book_data = self.word_exporter.assemble_full_book_structured_text([final_content], self.book_title)
            word_path = self.word_exporter.structured_text_to_word(book_data, f"{self.book_title}.docx", toc_depth=2)
            result["docx"] = word_path

        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed/60:.2f} minutes.")
        return result

    def _recursively_consolidate(self, nodes: List[Dict[str, Any]]):
        for node in nodes:
            if 'raw_content' in node and node['raw_content']:
                node['consolidated_content'] = self.concept_consolidator.consolidate_node_content(node['raw_content'])
            else:
                node['consolidated_content'] = ""
            if 'children' in node and node['children']:
                self._recursively_consolidate(node['children'])

    def _recursively_rewrite(self, nodes: List[Dict[str, Any]], parts: List[str], explained: List[str], level: int = 1, intent: Any = None):
        from src.interaction.command_parser import IntentResult
        
        for node in nodes:
            node_title = node['title']
            node_content = node.get('consolidated_content', '')
            
            if node_content.strip():
                # Use AcademicNoteWriter for high-quality structured notes
                depth = intent.depth if intent else "medium"
                
                rewritten = self.academic_writer.write_notes(
                    topic_name=node_title,
                    node_content=node_content,
                    explanation_depth=depth,
                    relationships=[], # Can be expanded with topic intelligence
                    already_explained=explained
                )
                
                if rewritten.strip():
                    # Ensure the heading level matches the hierarchy
                    # AcademicNoteWriter might generate its own headings, we standardize them here
                    content = re.sub(r'^(#+\s*.*?\n\n|\s*#+\s*.*?\n)', '', rewritten, count=1, flags=re.MULTILINE).strip()
                    parts.append(f"{'#' * level} {node_title}\n\n{content}\n\n")
                    explained.append(node_title)

            if 'children' in node and node['children']:
                self._recursively_rewrite(node['children'], parts, explained, level + 1, intent=intent)

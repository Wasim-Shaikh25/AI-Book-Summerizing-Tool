import os
import time
import logging
import re # Added import for regular expressions
from typing import Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.config import PDF_FOLDER, OUTPUT_FOLDER, CHUNK_SIZE_WORDS, ACTIVE_MODEL
from src.utils.pdf_reader import PDFReader
if ACTIVE_MODEL == "OLLAMA":
    from src.core.ollama.chunker import Chunker
    from src.core.ollama.embedder import Embedder
    from src.core.ollama.summarizer import Summarizer
elif ACTIVE_MODEL == "GEMINI":
    from src.core.gemini.chunker import Chunker
    from src.core.gemini.embedder import Embedder
    from src.core.gemini.summarizer import Summarizer
else:
    raise ValueError(f"Unsupported ACTIVE_MODEL: {ACTIVE_MODEL}")
from src.export.word_exporter import WordExporter


class SmartBookRewriterEnhanced:
    """
    A comprehensive pipeline for rewriting PDF book content into structured,
    exam-oriented notes, including chunking, embedding, core idea extraction,
    master knowledge brain creation, structured text rewriting, polishing,
    and export to Word (.docx).
    """

    def __init__(self, pdf_folder: str = PDF_FOLDER, output_folder: str = OUTPUT_FOLDER):
        self.pdf_folder = pdf_folder
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)
        self.book_title = "Rewritten Book Notes" # Default title

        self.pdf_reader = PDFReader(pdf_folder=self.pdf_folder)
        self.chunker = Chunker(chunk_size_words=CHUNK_SIZE_WORDS)
        self.embedder = Embedder(output_folder=self.output_folder)
        self.summarizer = Summarizer(active_model=ACTIVE_MODEL) # Initialize Summarizer with active model
        self.word_exporter = WordExporter(output_folder=self.output_folder)

    # ---------- Main run pipeline ----------
    def run(self) -> Dict[str, str]:
        """Executes the entire book rewriting pipeline."""
        start = time.time()
        
        try:
            full_text, self.book_title = self.pdf_reader.read_all_pdfs() # Store book_title as a class attribute
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Pipeline failed at PDF reading stage: {e}")
            return {"error": str(e)}

        chunks = self.chunker.chunk_text(full_text)
        if not chunks:
            logger.error("Pipeline failed: No chunks were generated from the PDF text.")
            return {"error": "No chunks generated."}

        # FAISS
        try:
            index, embeddings = self.embedder.build_faiss_index(chunks)
        except ValueError as e:
            logger.error(f"Pipeline failed at FAISS index building stage: {e}")
            return {"error": str(e)}

        # Extract core ideas
        core_ideas: List[str] = []
        logger.info("Extracting core ideas for each chunk...")
        for i, ch in enumerate(chunks):
            logger.info(f"  core ideas: chunk {i + 1}/{len(chunks)}")
            core = self.summarizer.extract_core_ideas(ch)
            core_ideas.append(core)
        
        if not core_ideas:
            logger.warning("No core ideas extracted. Master brain will be empty.")

        # Master brain
        master_brain = self.summarizer.create_master_brain(core_ideas)

        # Rewrite chunks to structured text
        structured_notes_list: List[str] = []
        logger.info("Rewriting chunks to structured text notes...")
        # Clarified additional context to be a thematic emphasis, not a literal title.
        additional_context_for_rewrite = "Ensure the content is like a new book, shorter, easy to understand in simple English, and exam-friendly. The overall theme to keep in mind is 'Understanding Contracts in Different Jurisdictions'."
        for i, ch in enumerate(chunks):
            logger.info(f"  rewriting chunk {i + 1}/{len(chunks)}")
            note_text = self.summarizer.rewrite_chunk_to_structured_notes(ch, master_brain, additional_context=additional_context_for_rewrite)
            
            # Polishing step removed as the chosen LLM is expected to handle it
            structured_notes_list.append(note_text)
        
        if not structured_notes_list:
            logger.error("No structured notes were generated from the chunks.")
            return {"error": "No structured notes generated."}

        # Assemble full book structured text data
        book_data = self.word_exporter.assemble_full_book_structured_text(structured_notes_list, self.book_title)

        # Save raw structured text (optional, for debugging/review)
        raw_text_path = self.word_exporter._save_text_file("\n\n--- CHAPTER BREAK ---\n\n".join(structured_notes_list), "rewritten_book_raw.txt")
        logger.info(f"Saved raw structured text: {raw_text_path}")

        # Convert to Word
        word_path = self.word_exporter.structured_text_to_word(book_data, f"{self.book_title}.docx")
        logger.info(f"Saved Word: {word_path}")

        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed/60:.2f} minutes.")
        return {"docx": word_path}


# ----------------- Run example -----------------
if __name__ == "__main__":
    rewriter = SmartBookRewriterEnhanced(pdf_folder=PDF_FOLDER, output_folder=OUTPUT_FOLDER)
    outputs = rewriter.run()
    logger.info(f"Outputs: {outputs}")

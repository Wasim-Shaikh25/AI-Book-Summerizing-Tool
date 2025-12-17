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

# Debugging: Print the active model to verify its value
print(f"DEBUG: ACTIVE_MODEL from config: {ACTIVE_MODEL}") # Added print for immediate visibility
logger.info(f"Configured ACTIVE_MODEL: {ACTIVE_MODEL}")

if ACTIVE_MODEL == "GEMINI":
    from src.core.gemini.chunker import Chunker
    from src.core.gemini.embedder import Embedder as GeminiEmbedder
    from src.core.gemini.summarizer import Summarizer as GeminiSummarizer
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
        
        if ACTIVE_MODEL == "GEMINI":
            self.embedder = GeminiEmbedder(output_folder=self.output_folder)
            self.summarizer = GeminiSummarizer(active_model=ACTIVE_MODEL)
        elif ACTIVE_MODEL == "GROK":
            self.embedder = GrokEmbedder(output_folder=self.output_folder)
            self.summarizer = GrokSummarizer(active_model=ACTIVE_MODEL)
        elif ACTIVE_MODEL == "OPENAI":
            self.embedder = OpenAIEmbedder(output_folder=self.output_folder)
            self.summarizer = OpenAISummarizer(active_model=ACTIVE_MODEL)
        else:
            raise ValueError(f"Unsupported ACTIVE_MODEL for Embedder/Summarizer initialization: {ACTIVE_MODEL}")
            
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
        existing_chapter_titles: List[str] = []
        
        logger.info("Rewriting chunks to structured text notes...")
        for i, ch in enumerate(chunks):
            logger.info(f"  rewriting chunk {i + 1}/{len(chunks)}")
            
            # Pass existing chapter titles as additional context
            additional_context_for_rewrite = (
                "Ensure the content is like a new book, shorter, easy to understand in simple English, and exam-friendly. "
                "The overall theme to keep in mind is 'Understanding Contracts in Different Jurisdictions'.\n"
                f"EXISTING_TOP_LEVEL_CHAPTER_TITLES: {existing_chapter_titles}\n"
                "Based on the above existing titles, determine if the current chunk's content is a sub-topic of an existing chapter "
                "or if it requires a new top-level chapter. If it's a sub-topic, propose a '## [Sub-topic Title]' instead of '# [Chapter Title]'."
            )
            
            note_text = self.summarizer.rewrite_chunk_to_structured_notes(ch, master_brain, additional_context=additional_context_for_rewrite)
            
            # Extract chapter title and add to existing_chapter_titles
            chapter_title_match = re.search(r"^#\s*(.+)$", note_text, re.MULTILINE)
            if chapter_title_match:
                title = chapter_title_match.group(1).strip()
                if title not in existing_chapter_titles:
                    existing_chapter_titles.append(title)
            
            structured_notes_list.append(note_text)
        
        if not structured_notes_list:
            logger.error("No structured notes were generated from the chunks.")
            return {"error": "No structured notes generated."}

        # Post-process notes to enforce hierarchy and reduce repetition
        final_structured_notes = self._post_process_notes_for_hierarchy(structured_notes_list)

        # Assemble full book structured text data
        book_data = self.word_exporter.assemble_full_book_structured_text(final_structured_notes, self.book_title)

        # Save raw structured text (optional, for debugging/review)
        raw_text_path = self.word_exporter._save_text_file("\n\n--- CHAPTER BREAK ---\n\n".join(structured_notes_list), "rewritten_book_raw.txt")
        logger.info(f"Saved raw structured text: {raw_text_path}")

        # Convert to Word
        word_path = self.word_exporter.structured_text_to_word(book_data, f"{self.book_title}.docx", toc_depth=2) # Changed toc_depth to 2
        logger.info(f"Saved Word: {word_path}")

        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed/60:.2f} minutes.")
        return {"docx": word_path}

    def _post_process_notes_for_hierarchy(self, structured_notes_list: List[str]) -> List[str]:
        """
        Post-processes the generated notes to enforce a hierarchical chapter structure,
        grouping related content under main chapters and converting repetitive titles
        into sub-topics.
        """
        final_structured_notes: List[str] = []
        top_level_chapters: Dict[str, List[str]] = {} # Stores {chapter_title: [list of sub-topics/notes]}
        
        logger.info("Post-processing notes for hierarchical organization...")

        for note_text in structured_notes_list:
            chapter_title_match = re.search(r"^#\s*(.+)$", note_text, re.MULTILINE)
            summary_match = re.search(r"^\*\*Summary:\*\*\s*(.+)", note_text, re.MULTILINE)
            
            current_title = chapter_title_match.group(1).strip() if chapter_title_match else "Untitled Chapter"
            current_summary = summary_match.group(1).strip() if summary_match else ""

            # More robust keyword-based similarity check for grouping
            found_parent = False
            best_parent_title = None
            highest_similarity = 0.0
            
            # Extract keywords from current title and summary
            current_keywords = set(word.lower() for word in re.findall(r'\b\w+\b', current_title + " " + current_summary) if len(word) > 2)

            for existing_chapter_title in top_level_chapters.keys():
                # Extract keywords from existing chapter title
                existing_keywords = set(word.lower() for word in re.findall(r'\b\w+\b', existing_chapter_title) if len(word) > 2)
                
                # Calculate Jaccard similarity between current and existing chapter keywords
                intersection = len(current_keywords.intersection(existing_keywords))
                union = len(current_keywords.union(existing_keywords))
                
                similarity = intersection / union if union > 0 else 0.0

                # Define a threshold for considering it a sub-topic
                # This threshold might need tuning based on content
                SIMILARITY_THRESHOLD = 0.6 # Increased similarity threshold for stricter grouping

                if similarity > highest_similarity and similarity >= SIMILARITY_THRESHOLD:
                    highest_similarity = similarity
                    best_parent_title = existing_chapter_title
            
            if best_parent_title:
                # If a strong parent is found, convert the current note to a sub-topic
                logger.info(f"  Converting '{current_title}' to sub-topic under '{best_parent_title}' (Similarity: {highest_similarity:.2f})")
                
                # Replace the '# Chapter Title:' with '## Sub-topic Title:'
                # And remove the summary as sub-topics usually don't need a separate summary
                modified_note_text = re.sub(r"^#\s*(.+)$", f"## \\1", note_text, flags=re.MULTILINE)
                modified_note_text = re.sub(r"^\*\*Summary:\*\*\s*.+\n", "", modified_note_text, flags=re.MULTILINE)
                
                top_level_chapters[best_parent_title].append(modified_note_text)
                found_parent = True
            
            if not found_parent:
                # If no suitable parent found, create a new top-level chapter
                logger.info(f"  Creating new top-level chapter: '{current_title}'")
                top_level_chapters[current_title] = [note_text] # Add the original note as the first item
        
        # Assemble the final list of notes with enforced hierarchy
        for chapter_title, notes in top_level_chapters.items():
            # The first note in each group is the main chapter, others are sub-topics
            # We need to ensure the first note is indeed a '# Chapter Title:'
            # and subsequent ones are '## Sub-topic Title:'
            
            # Ensure the first note is a top-level chapter
            first_note = notes[0]
            if not re.search(r"^#\s", first_note, re.MULTILINE):
                # If the first note somehow became a sub-topic, promote it
                first_note = re.sub(r"^##\s*(.+)$", r"# \1", first_note, flags=re.MULTILINE)
                
            final_structured_notes.append(first_note)
            
            for i in range(1, len(notes)):
                sub_topic_note = notes[i]
                # Ensure subsequent notes are sub-topics
                if re.search(r"^#\s", sub_topic_note, re.MULTILINE):
                    # If a sub-topic mistakenly has a chapter title, demote it
                    sub_topic_note = re.sub(r"^#\s*(.+)$", r"## \1", sub_topic_note, flags=re.MULTILINE)
                final_structured_notes.append(sub_topic_note)
                
        logger.info("Notes post-processing complete.")
        return final_structured_notes


# ----------------- Run example -----------------
if __name__ == "__main__":
    rewriter = SmartBookRewriterEnhanced(pdf_folder=PDF_FOLDER, output_folder=OUTPUT_FOLDER)
    outputs = rewriter.run()
    logger.info(f"Outputs: {outputs}")

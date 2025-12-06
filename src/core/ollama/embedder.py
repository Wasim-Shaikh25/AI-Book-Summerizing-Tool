import logging
from typing import List, Any, Tuple
import os

import faiss
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL, OUTPUT_FOLDER

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self, embedding_model: str = EMBEDDING_MODEL, output_folder: str = OUTPUT_FOLDER):
        self.output_folder = output_folder
        logger.info("Loading embedding model (SentenceTransformer)...")
        self.embedder = SentenceTransformer(embedding_model)

    def build_faiss_index(self, chunks: List[str]) -> Tuple[Any, Any]:
        """Embeds text chunks and builds a FAISS index."""
        logger.info("Embedding chunks and building FAISS index...")
        if not chunks:
            raise ValueError("Cannot build FAISS index with empty chunks.")
        
        embeddings = self.embedder.encode(chunks, show_progress_bar=True, convert_to_numpy=True)
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        faiss.write_index(index, os.path.join(self.output_folder, "book_faiss.index"))
        logger.info("FAISS index saved.")
        return index, embeddings

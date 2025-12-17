import logging
from typing import List, Any, Tuple
import os

import faiss
import tensorflow_hub as hub
import numpy as np

from src.config import OUTPUT_FOLDER

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self, output_folder: str = OUTPUT_FOLDER):
        self.output_folder = output_folder
        logger.info("Loading Universal Sentence Encoder model from TensorFlow Hub for Grok...")
        self.model = hub.load("https://tfhub.dev/google/universal-sentence-encoder/4")

    def build_faiss_index(self, chunks: List[str]) -> Tuple[Any, Any]:
        """Embeds text chunks using Universal Sentence Encoder and builds a FAISS index for Grok."""
        logger.info("Embedding chunks and building FAISS index using Universal Sentence Encoder for Grok...")
        if not chunks:
            raise ValueError("Cannot build FAISS index with empty chunks.")
        
        embeddings = self.model(chunks).numpy().astype('float32')
        
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        faiss.write_index(index, os.path.join(self.output_folder, "book_faiss.index"))
        logger.info("FAISS index saved for Grok.")
        return index, embeddings

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
        logger.info("Loading Universal Sentence Encoder model from TensorFlow Hub for Gemini...")
        self.model = hub.load("https://tfhub.dev/google/universal-sentence-encoder/4")

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generates embeddings for a list of texts."""
        return self.model(texts).numpy().astype('float32')

    def get_similarity_scores(self, query_embedding: np.ndarray, document_embeddings: np.ndarray) -> np.ndarray:
        """Calculates cosine similarity between a query embedding and document embeddings."""
        # Normalize embeddings to unit vectors for cosine similarity
        query_embedding_norm = query_embedding / np.linalg.norm(query_embedding)
        document_embeddings_norm = document_embeddings / np.linalg.norm(document_embeddings, axis=1, keepdims=True)
        
        # Cosine similarity is the dot product of normalized vectors
        return np.dot(document_embeddings_norm, query_embedding_norm)

    def build_faiss_index(self, chunks: List[str]) -> Tuple[Any, Any]:
        """Embeds text chunks using Universal Sentence Encoder and builds a FAISS index for Gemini."""
        logger.info("Embedding chunks and building FAISS index using Universal Sentence Encoder for Gemini...")
        if not chunks:
            raise ValueError("Cannot build FAISS index with empty chunks.")
        
        embeddings = self.get_embeddings(chunks)
        
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        faiss.write_index(index, os.path.join(self.output_folder, "book_faiss.index"))
        logger.info("FAISS index saved.")
        return index, embeddings

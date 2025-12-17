import logging
from typing import List, Any, Tuple
import os

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings
import tiktoken

from src.config import OUTPUT_FOLDER, OPENAI_API_KEY

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self, output_folder: str = OUTPUT_FOLDER):
        self.output_folder = output_folder
        logger.info("Initializing OpenAI Embeddings model...")
        self.model = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a list of texts using OpenAI."""
        return self.model.embed_documents(texts)

    def build_faiss_index(self, chunks: List[str]) -> Tuple[Any, Any]:
        """Embeds text chunks using OpenAI and builds a FAISS index."""
        logger.info("Embedding chunks and building FAISS index using OpenAI...")
        if not chunks:
            raise ValueError("Cannot build FAISS index with empty chunks.")
        
        embeddings = np.array(self._get_embeddings(chunks)).astype('float32')
        
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        faiss.write_index(index, os.path.join(self.output_folder, "book_faiss_openai.index"))
        logger.info("FAISS index saved for OpenAI.")
        return index, embeddings

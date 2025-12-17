import logging
from typing import List

from src.config import CHUNK_SIZE_WORDS

logger = logging.getLogger(__name__)

class Chunker:
    def __init__(self, chunk_size_words: int = CHUNK_SIZE_WORDS):
        self.chunk_size_words = chunk_size_words

    def chunk_text(self, text: str) -> List[str]:
        """Splits the input text into chunks of a specified word size."""
        words = text.split()
        chunks: List[str] = []
        for i in range(0, len(words), self.chunk_size_words):
            chunk = " ".join(words[i:i + self.chunk_size_words])
            chunks.append(chunk.strip())
        logger.info(f"Chunked text into {len(chunks)} chunks (size ~{self.chunk_size_words} words).")
        return chunks

import logging
import json
import re
import hashlib
from typing import List, Optional, Any
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_CLEAN_AND_SEMANTIC_CHUNK
from src.config import CHUNK_SIZE_WORDS

logger = logging.getLogger(__name__)

class Chunker:
    def __init__(self, chunk_size_words: int = CHUNK_SIZE_WORDS):
        self.chunk_size_words = chunk_size_words
        self.client = GeminiClient()

    def chunk_text(self, text: str) -> List[str]:
        """Splits the input text into chunks of a specified word size."""
        words = text.split()
        chunks: List[str] = []
        for i in range(0, len(words), self.chunk_size_words):
            chunk = " ".join(words[i:i + self.chunk_size_words])
            chunks.append(chunk.strip())
        logger.info(f"Chunked text into {len(chunks)} chunks (size ~{self.chunk_size_words} words).")
        return chunks

    async def _process_block_async(self, block: str, block_index: int, trace: Optional[Any] = None) -> List[str]:
        """
        Asynchronously processes a single block for semantic chunking.
        """
        logger.info(f"Processing block {block_index} for semantic chunking...")
        prompt = PROMPT_CLEAN_AND_SEMANTIC_CHUNK.format(raw_text=block)
        
        try:
            from src.core.gemini.async_client import GeminiAsyncClient
            async_client = GeminiAsyncClient()
            response = await async_client.generate(
                prompt=prompt,
                trace=trace,
                task_name=f"semantic_chunking_block_{block_index}",
                generation_config={"temperature": 0.1}
            )
            
            if response:
                # Clean response if it contains markdown fences
                clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
                # Robust JSON parsing
                start_idx = clean_response.find('{')
                end_idx = clean_response.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    clean_response = clean_response[start_idx:end_idx+1]
                
                data = json.loads(clean_response)
                return data.get("chunks", [])
        except Exception as e:
            logger.error(f"Failed to process block {block_index}: {e}")
        
        return [block] # Fallback

    def semantic_chunking(self, text: str, trace: Optional[Any] = None) -> List[str]:
        """
        Performs parallel semantic chunking and noise removal using asyncio.
        """
        logger.info("Starting parallel semantic chunking and noise removal...")
        
        initial_chunks = self.chunk_text(text)
        
        blocks = []
        current_block = []
        current_word_count = 0
        for chunk in initial_chunks:
            words = chunk.split()
            if current_word_count + len(words) > 4000:
                blocks.append(" ".join(current_block))
                current_block = [chunk]
                current_word_count = len(words)
            else:
                current_block.append(chunk)
                current_word_count += len(words)
        if current_block:
            blocks.append(" ".join(current_block))

        # Parallel Execution Boundary
        from src.utils.async_manager import AsyncExecutionManager
        async_manager = AsyncExecutionManager(max_concurrency=5, trace=trace)
        
        task_names = [f"chunking_block_{i+1}" for i in range(len(blocks))]
        # Pass (func, args, kwargs) tuples instead of coroutines
        task_defs = [(self._process_block_async, (block, i+1, trace), {}) for i, block in enumerate(blocks)]
        batch_results = async_manager.run_parallel(task_defs, task_names=task_names)
        
        all_semantic_chunks = []
        for result in batch_results:
            if result:
                all_semantic_chunks.extend(result)
        
        # ASSERT: No duplicate content (using hash for efficiency)
        seen_hashes = set()
        unique_chunks = []
        for chunk in all_semantic_chunks:
            chunk_hash = hashlib.md5(chunk.encode()).hexdigest()
            if chunk_hash not in seen_hashes:
                unique_chunks.append(chunk)
                seen_hashes.add(chunk_hash)
        
        logger.info(f"Semantic chunking complete. Extracted {len(unique_chunks)} unique clean chunks.")
        return unique_chunks

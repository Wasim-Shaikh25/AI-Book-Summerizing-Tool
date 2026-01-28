import asyncio
import logging
import google.generativeai as genai
from datetime import datetime
from typing import Optional, Dict, Any
from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.utils.execution_trace import ExecutionTrace

logger = logging.getLogger(__name__)

class GeminiAsyncClient:
    """
    A dedicated asynchronous client for Google Gemini with concurrency control,
    retries, and timeout handling.
    """
    def __init__(self, model_name: str = GEMINI_MODEL, max_concurrent: int = 5):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        
        genai.configure(api_key=GEMINI_API_KEY)
        self.model_name = model_name
        self.model = None # Initialized lazily per loop
        self.max_concurrent = max_concurrent
        self._semaphore = None
        self._model_loop = None
        self._sem_loop = None
        self.timeout = 60 # Default timeout in seconds

    def _get_model(self):
        """Ensures the GenerativeModel is bound to the current event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return self.model

        if self._model_loop != current_loop or self.model is None:
            # Loop changed or first run, re-initialize model to refresh gRPC state
            self.model = genai.GenerativeModel(self.model_name)
            self._model_loop = current_loop
        
        return self.model

    def _get_semaphore(self):
        """Lazily creates or refreshes the semaphore for the current event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        if self._sem_loop != current_loop or self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
            self._sem_loop = current_loop
        
        return self._semaphore

    async def generate(self, prompt: str, trace: Optional[ExecutionTrace] = None, task_name: str = "gemini_gen", generation_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Asynchronously generates content from Gemini with retries and concurrency control.
        """
        config = generation_config or {
            "temperature": 0.1,
            "top_p": 1,
            "top_k": 1,
        }

        start_time = datetime.utcnow().isoformat()
        sem = self._get_semaphore()
        async with sem:
            try:
                return await self._execute_with_retry(prompt, config, task_name, trace, start_time)
            except Exception as e:
                if trace:
                    trace.log_stage(
                        agent="GeminiAsyncClient",
                        action="generate",
                        status="failed",
                        task_name=task_name,
                        start_time=start_time,
                        confidence=0.0
                    )
                logger.error(f"GeminiAsyncClient critical failure for '{task_name}': {e}")
                raise e

    async def _execute_with_retry(self, prompt: str, config: Dict[str, Any], task_name: str, trace: Optional[ExecutionTrace], start_time: str) -> str:
        """
        Internal helper to handle single retry on transient failures.
        """
        attempts = 2 # Initial attempt + 1 retry
        model = self._get_model()
        
        for attempt in range(attempts):
            try:
                response = await asyncio.wait_for(
                    model.generate_content_async(prompt, generation_config=config),
                    timeout=self.timeout
                )
                
                if not response or not response.text:
                    raise Exception("Gemini returned an empty response.")
                
                if trace:
                    trace.log_stage(
                        agent="GeminiAsyncClient",
                        action="generate",
                        status="passed",
                        task_name=task_name,
                        start_time=start_time,
                        retry_count=attempt
                    )
                return response.text.strip()

            except (asyncio.TimeoutError, Exception) as e:
                is_transient = isinstance(e, asyncio.TimeoutError) or "429" in str(e)
                
                if is_transient and attempt < attempts - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"Transient error detected for '{task_name}': {e}. Retrying...")
                    await asyncio.sleep(wait_time)
                    continue
                raise e

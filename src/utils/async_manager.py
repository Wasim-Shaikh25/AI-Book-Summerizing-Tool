import asyncio
import logging
from datetime import datetime
from typing import List, Any, Callable, Coroutine, TypeVar, Optional, Tuple

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Global persistent loop to prevent gRPC/EventLoop closure issues
_GLOBAL_LOOP = None

class AsyncExecutionManager:
    """
    Manages asynchronous execution of tasks with concurrency control, 
    retries, and timeouts, while providing a synchronous interface.
    """
    def __init__(self, max_concurrency: int = 5, retries: int = 3, timeout: int = 60, trace: Optional[Any] = None):
        self.max_concurrency = max_concurrency
        self.retries = retries
        self.timeout = timeout
        self.trace = trace
        self._semaphore = None

    def _get_loop(self):
        """Returns a persistent event loop."""
        global _GLOBAL_LOOP
        if _GLOBAL_LOOP is None or _GLOBAL_LOOP.is_closed():
            try:
                _GLOBAL_LOOP = asyncio.get_event_loop()
            except RuntimeError:
                _GLOBAL_LOOP = asyncio.new_event_loop()
                asyncio.set_event_loop(_GLOBAL_LOOP)
        return _GLOBAL_LOOP

    def _get_semaphore(self):
        """Lazily creates the semaphore within the active event loop."""
        if self._semaphore is None:
            # In modern Python (3.10+), Semaphore uses the running loop automatically
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
        return self._semaphore

    async def _execute_with_retry(self, func: Callable[..., Coroutine[Any, Any, T]], args: Tuple, kwargs: dict, task_name: str) -> T:
        """
        Internal helper to execute a coroutine factory with retry logic and semaphore.
        Re-creates the coroutine on each attempt to avoid 'already awaited' errors.
        """
        start_time = datetime.utcnow().isoformat()
        last_exception = None
        sem = self._get_semaphore()
        
        for attempt in range(self.retries):
            try:
                async with sem:
                    # Re-create the coroutine on each attempt
                    coro = func(*args, **kwargs)
                    result = await asyncio.wait_for(coro, timeout=self.timeout)
                    
                    if self.trace:
                        self.trace.log_stage(
                            agent="AsyncManager",
                            action="execute_task",
                            status="passed",
                            task_name=task_name,
                            start_time=start_time,
                            retry_count=attempt
                        )
                    return result
            except (asyncio.TimeoutError, Exception) as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1} for '{task_name}' failed: {e}")
            
            if attempt < self.retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        if self.trace:
            self.trace.log_stage(
                agent="AsyncManager",
                action="execute_task",
                status="failed",
                task_name=task_name,
                start_time=start_time,
                retry_count=self.retries,
                confidence=0.0
            )
        
        logger.error(f"All {self.retries} attempts failed for '{task_name}'.")
        return None

    def run_parallel(self, task_defs: List[Tuple[Callable[..., Coroutine[Any, Any, T]], Tuple, dict]], task_names: Optional[List[str]] = None) -> List[T]:
        """
        Runs multiple coroutine factories in parallel and returns fully resolved results.
        task_defs: List of (async_func, args, kwargs)
        """
        if not task_defs:
            return []

        if not task_names:
            task_names = [f"task_{i}" for i in range(len(task_defs))]

        async def _orchestrate():
            # Ensure semaphore is created inside the loop context
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
            
            tasks = [self._execute_with_retry(f, a, k, name) for (f, a, k), name in zip(task_defs, task_names)]
            return await asyncio.gather(*tasks)

        try:
            # Use a persistent loop to avoid gRPC/EventLoop closure issues between phases.
            loop = self._get_loop()
            if loop.is_running():
                # If already in a loop, we might need a different approach, 
                # but for this CLI app, run_until_complete is usually called from sync context.
                import nest_asyncio
                nest_asyncio.apply(loop)
            return loop.run_until_complete(_orchestrate())
        except Exception as e:
            logger.error(f"Async orchestration failed: {e}")
            return [None] * len(task_defs)

    def run_single(self, func: Callable[..., Coroutine[Any, Any, T]], args: Tuple = (), kwargs: dict = None, task_name: str = "single_task") -> T:
        """
        Runs a single coroutine factory synchronously.
        """
        return self.run_parallel([(func, args, kwargs or {})], [task_name])[0]

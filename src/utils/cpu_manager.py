import os
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any, Callable

logger = logging.getLogger(__name__)

class CPUExecutionManager:
    """
    Manages CPU-bound tasks using a ThreadPoolExecutor.
    Strictly limited to non-IO, non-LLM, non-DB tasks.
    """
    def __init__(self):
        # Limit workers to min(4, cpu_count) as per requirements
        cpu_count = os.cpu_count() or 1
        self.max_workers = min(4, cpu_count)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        logger.info(f"CPUExecutionManager initialized with {self.max_workers} workers.")

    def run_parallel(self, func: Callable, items: List[Any]) -> List[Any]:
        """
        Runs a CPU-bound function over a list of items in parallel.
        """
        if not items:
            return []
        
        logger.debug(f"Running CPU-bound task '{func.__name__}' on {len(items)} items.")
        return list(self.executor.map(func, items))

    def shutdown(self):
        """Shuts down the executor."""
        self.executor.shutdown(wait=True)

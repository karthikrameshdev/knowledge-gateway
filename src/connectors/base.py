from abc import ABC, abstractmethod
import asyncio
from typing import List, Dict, Any
from ..models import GatewayKnowledgeItem


class BaseConnector(ABC):
    """Abstract interface that all Knowledge Gateway connectors implement."""

    def __init__(self, name: str, source_type: str, enabled: bool = True):
        self.name = name
        self.source_type = source_type
        self.enabled = enabled
        self._workers = asyncio.Semaphore(4)
        self._jobs = set()

    async def run_blocking(self, function, *args):
        """Bound synchronous I/O without blocking the event loop or releasing timed-out workers early."""
        await self._workers.acquire()
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        self._jobs.add(task)
        def finished(job):
            self._jobs.discard(job)
            self._workers.release()
            if not job.cancelled():
                job.exception()  # consume failures if its HTTP caller already timed out
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def aclose(self):
        if self._jobs:
            await asyncio.gather(*self._jobs, return_exceptions=True)

    @abstractmethod
    async def search(
        self,
        query: str,
        tags: List[str],
        top_k: int = 5,
    ) -> List[GatewayKnowledgeItem]:
        """Executes search against this specific source and returns standardized items."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Returns connection and status health information."""
        pass

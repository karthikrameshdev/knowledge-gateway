import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional, AsyncGenerator, Set
from .models import ActivityLogEntry

logger = logging.getLogger("GatewayLogger")


class ActivityLogger:
    """In-memory audit log and real-time Server-Sent Events (SSE) tailing broadcaster."""

    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self._entries: deque[ActivityLogEntry] = deque(maxlen=max_entries)
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    def record(self, entry: ActivityLogEntry) -> None:
        """Stores an activity entry and broadcasts it to live tailing subscribers."""
        self._entries.appendleft(entry)

        # Broadcast to any active SSE subscribers
        event_data = {
            "request_id": entry.request_id,
            "timestamp": entry.timestamp,
            "query": entry.query,
            "tags": entry.tags,
            "latency_ms": entry.latency_ms,
            "status_code": entry.status_code,
            "sources_attempted": entry.sources_attempted,
            "source_breakdown": entry.source_breakdown,
            "items_returned_count": entry.items_returned_count,
            "total_consolidated_items": entry.total_consolidated_items,
            "top_score": entry.top_score,
            "page": entry.page,
            "page_size": entry.page_size,
            "cached": entry.cached,
            "cache_backend": entry.cache_backend,
        }
        msg = f"data: {json.dumps(event_data)}\n\n"

        dead_queues = set()
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead_queues.add(q)
            except Exception:
                dead_queues.add(q)

        self._subscribers -= dead_queues

    def get_entries(
        self,
        limit: int = 50,
        offset: int = 0,
        query_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
    ) -> List[ActivityLogEntry]:
        """Retrieves paginated and filtered activity log entries."""
        filtered = list(self._entries)

        if query_filter:
            q_clean = query_filter.lower().strip()
            filtered = [
                e for e in filtered
                if q_clean in e.query.lower() or q_clean in e.request_id.lower()
            ]

        if source_filter:
            s_clean = source_filter.lower().strip()
            filtered = [
                e for e in filtered
                if any(s_clean == s.lower() for s in e.sources_attempted)
            ]

        return filtered[offset : offset + limit]

    def get_entry_by_id(self, request_id: str) -> Optional[ActivityLogEntry]:
        """Finds entry by request_id."""
        for e in self._entries:
            if e.request_id == request_id:
                return e
        return None

    def get_total_count(self) -> int:
        return len(self._entries)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribes an async generator to live Server-Sent Events."""
        q = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        try:
            # Send initial ping event
            yield f": connected at {datetime.now(timezone.utc).isoformat()}\n\n"
            while True:
                data = await q.get()
                yield data
        finally:
            self._subscribers.discard(q)


# Global singleton logger
global_activity_logger = ActivityLogger()

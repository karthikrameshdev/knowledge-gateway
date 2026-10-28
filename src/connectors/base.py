from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ..models import GatewayKnowledgeItem


class BaseConnector(ABC):
    """Abstract interface that all Knowledge Gateway connectors implement."""

    def __init__(self, name: str, source_type: str, enabled: bool = True):
        self.name = name
        self.source_type = source_type
        self.enabled = enabled

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

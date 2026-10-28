import math
import hashlib
import logging
from typing import List, Dict, Any, Optional
import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .base import BaseConnector
from ..models import GatewayKnowledgeItem
from ..config import RAGConfig

logger = logging.getLogger("RAGConnector")


class EmbeddingClient:
    """Handles text embeddings via OpenAI-compatible API with deterministic fallback."""

    def __init__(
        self,
        openai_url: str = "https://openrouter.ai/api/v1",
        model_id: str = "openai/text-embedding-3-small",
        api_key: str = "",
        dimension: int = 768,
    ):
        self.openai_url = openai_url.rstrip("/")
        self.model_id = model_id
        self.api_key = api_key
        self.dimension = dimension

    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        # Attempt OpenAI-compatible endpoint if API key exists
        if self.api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                # Standard OpenAI embedding URL
                url = f"{self.openai_url}/embeddings"
                payload = {
                    "model": self.model_id,
                    "input": texts,
                }
                with httpx.Client(timeout=6.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        vectors = []
                        for item in data:
                            raw_vec = item.get("embedding", [])
                            # Normalize / fit dimension
                            if len(raw_vec) > self.dimension:
                                vec = raw_vec[:self.dimension]
                            else:
                                vec = raw_vec + [0.0] * (self.dimension - len(raw_vec))
                            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
                            vectors.append([x / norm for x in vec])
                        if vectors and len(vectors) == len(texts):
                            return vectors
            except Exception as e:
                logger.debug("OpenAI embedding API call failed: %s. Using deterministic fallback.", e)

        # Fast deterministic semantic fallback
        return [self._deterministic_vector(t) for t in texts]

    def _deterministic_vector(self, text: str) -> List[float]:
        """Deterministic pseudo-semantic L2-normalized vector for testing and offline runs."""
        vec = [0.0] * self.dimension
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec

        for word in words:
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            weight = math.log(1.0 + len(word))
            vec[idx] += sign * weight

            # Bigram enhancement
            for i in range(len(word) - 1):
                bg = word[i : i + 2]
                h_bg = int(hashlib.md5(bg.encode("utf-8")).hexdigest(), 16)
                idx_bg = h_bg % self.dimension
                vec[idx_bg] += 0.5 * (1.0 if ((h_bg >> 4) & 1) else -1.0)

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class RAGConnector(BaseConnector):
    """Retrieval-Augmented Generation connector for Qdrant Vector Database."""

    def __init__(self, config: RAGConfig):
        super().__init__(name="rag_vector_db", source_type="rag", enabled=config.enabled)
        self.config = config
        self.embedder = EmbeddingClient(
            openai_url=config.embedding.openai_url,
            model_id=config.embedding.model_id,
            api_key=config.embedding.api_key,
            dimension=config.embedding.dimension,
        )
        self.client: Optional[QdrantClient] = None
        self.is_connected = False
        self.backend_type = "uninitialized"
        if self.enabled:
            self._connect()

    def _connect(self):
        try:
            self.client = QdrantClient(
                host=self.config.host,
                port=self.config.port,
                timeout=3.0,
                check_compatibility=False,
            )
            # Ping
            self.client.get_collections()
            self.is_connected = True
            self.backend_type = f"Docker / Remote Qdrant ({self.config.host}:{self.config.port})"
            logger.info("RAG Connector connected to Qdrant at %s:%s", self.config.host, self.config.port)
            self._ensure_collection()
        except Exception as e:
            logger.warning("Could not reach Qdrant at %s:%s (%s). Using embedded memory mode.", self.config.host, self.config.port, e)
            self.client = QdrantClient(location=":memory:", check_compatibility=False)
            self.is_connected = True
            self.backend_type = "Embedded In-Memory Qdrant"
            self._ensure_collection()

    def _ensure_collection(self):
        if not self.client:
            return
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.config.collection for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.config.collection,
                    vectors_config=qmodels.VectorParams(
                        size=self.config.embedding.dimension,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection: %s", self.config.collection)
        except Exception as e:
            logger.error("Error creating Qdrant collection %s: %s", self.config.collection, e)

    def index_seed_documents(self, documents: List[Dict[str, Any]]):
        """Indexes sample documents into the Qdrant vector collection."""
        if not self.client or not documents:
            return

        texts = [f"{d.get('title', '')}\n{d.get('content', '')}" for d in documents]
        vectors = self.embedder.embed_batch(texts)

        points = []
        for i, (doc, vec) in enumerate(zip(documents, vectors)):
            points.append(
                qmodels.PointStruct(
                    id=i + 1,
                    vector=vec,
                    payload={
                        "id": doc.get("id", f"rag_chunk_{i+1}"),
                        "title": doc.get("title", f"Document {i+1}"),
                        "content": doc.get("content", ""),
                        "category": doc.get("category", "general"),
                        "tags": doc.get("tags", []),
                        "source_file": doc.get("source_file", "rag_store"),
                        "metadata": doc.get("metadata", {}),
                    },
                )
            )

        self.client.upsert(
            collection_name=self.config.collection,
            points=points,
        )
        logger.info("Indexed %d seed points into Qdrant collection %s", len(points), self.config.collection)

    async def search(
        self,
        query: str,
        tags: List[str],
        top_k: int = 5,
    ) -> List[GatewayKnowledgeItem]:
        if not self.enabled or not self.client:
            return []

        limit = min(top_k or self.config.top_k, 20)
        query_vec = self.embedder.embed_text(query)

        try:
            search_result = self.client.query_points(
                collection_name=self.config.collection,
                query=query_vec,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            items = []
            for scored in search_result.points:
                payload = scored.payload or {}
                content = str(payload.get("content", ""))
                snippet = content[:200] + ("..." if len(content) > 200 else "")
                score = float(scored.score)

                item = GatewayKnowledgeItem(
                    id=str(payload.get("id", f"rag_point_{scored.id}")),
                    source_type="rag",
                    title=str(payload.get("title", f"RAG Result {scored.id}")),
                    content=content,
                    snippet=snippet,
                    raw_score=score,
                    provenance={
                        "connector": "rag_vector_db",
                        "point_id": scored.id,
                        "collection": self.config.collection,
                        "embedding_model": self.config.embedding.model_id,
                        "openai_url": self.config.embedding.openai_url,
                        "dimension": self.config.embedding.dimension,
                    },
                    metadata={
                        "category": payload.get("category", "general"),
                        "tags": payload.get("tags", []),
                        "source_file": payload.get("source_file", "vector_store"),
                    },
                )
                items.append(item)

            return items
        except Exception as e:
            logger.error("RAG search failed: %s", e)
            return []

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "connector": self.name}
        try:
            info = self.client.get_collection(self.config.collection)
            return {
                "status": "healthy",
                "connector": self.name,
                "backend": self.backend_type,
                "collection": self.config.collection,
                "points_count": getattr(info, "points_count", 0),
                "embedding_model": self.config.embedding.model_id,
                "openai_url": self.config.embedding.openai_url,
                "dimension": self.config.embedding.dimension,
            }
        except Exception as e:
            return {
                "status": "degraded",
                "connector": self.name,
                "backend": self.backend_type,
                "error": str(e),
            }

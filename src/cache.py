import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .config import CacheConfig
from .models import GatewayQuery, GatewayResponse

logger = logging.getLogger("GatewayCache")


class BaseCache(ABC):
    """Abstract cache provider interface."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        pass


class InMemoryCache(BaseCache):
    """High-speed in-memory cache supporting TTL expiration and LRU/LFU/FIFO eviction."""

    def __init__(
        self,
        max_entries: int = 1000,
        default_ttl: int = 300,
        eviction_policy: str = "lru",
    ):
        self.max_entries = max(1, max_entries)
        self.default_ttl = default_ttl
        self.eviction_policy = eviction_policy.lower()
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return None

            # Check expiration
            if entry["expires_at"] and now > entry["expires_at"]:
                del self._store[key]
                self.misses += 1
                return None

            # Update access telemetry
            entry["last_accessed"] = now
            entry["access_count"] += 1
            self.hits += 1
            return entry["val"]

    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = now + ttl if ttl > 0 else None

        async with self._lock:
            # Check capacity & evict if necessary
            if len(self._store) >= self.max_entries and key not in self._store:
                self._evict_one(now)

            self._store[key] = {
                "val": value,
                "expires_at": expires_at,
                "created_at": now,
                "last_accessed": now,
                "access_count": 1,
            }

    def _evict_one(self, now: float):
        """Evicts expired entries or applies eviction policy (LRU, LFU, FIFO)."""
        # 1. Clean expired entries first
        expired = [k for k, v in self._store.items() if v["expires_at"] and now > v["expires_at"]]
        if expired:
            for k in expired:
                del self._store[k]
                self.evictions += 1
            return

        if not self._store:
            return

        # 2. Policy-based eviction
        target_key = None
        if self.eviction_policy == "lfu":
            # Least frequently used
            target_key = min(self._store.keys(), key=lambda k: self._store[k]["access_count"])
        elif self.eviction_policy == "fifo":
            # First in first out
            target_key = min(self._store.keys(), key=lambda k: self._store[k]["created_at"])
        else:
            # Default: LRU (least recently used)
            target_key = min(self._store.keys(), key=lambda k: self._store[k]["last_accessed"])

        if target_key:
            del self._store[target_key]
            self.evictions += 1

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        ratio = round((self.hits / float(total)) * 100, 1) if total > 0 else 0.0
        return {
            "backend": "in_memory",
            "active_entries": len(self._store),
            "max_entries": self.max_entries,
            "eviction_policy": self.eviction_policy,
            "ttl_seconds": self.default_ttl,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_ratio_percent": ratio,
        }


class RedisCache(BaseCache):
    """Production Redis caching layer with automatic fallback to in-memory cache."""

    def __init__(self, config: CacheConfig):
        self.config = config
        self.redis_cfg = config.redis
        self.client = None
        self.is_connected = False
        self.hits = 0
        self.misses = 0
        self.prefix = self.redis_cfg.key_prefix
        # In-memory fallback
        self.memory_fallback = InMemoryCache(
            max_entries=config.max_entries,
            default_ttl=config.ttl_seconds,
            eviction_policy=config.eviction_policy,
        )
        self._init_redis()

    def _init_redis(self):
        try:
            import redis.asyncio as aioredis
            self.client = aioredis.Redis(
                host=self.redis_cfg.host,
                port=self.redis_cfg.port,
                db=self.redis_cfg.db,
                password=self.redis_cfg.password or None,
                socket_timeout=self.redis_cfg.timeout_seconds,
                decode_responses=True,
            )
            logger.info("Configured Redis cache connection to %s:%s (db: %s)", self.redis_cfg.host, self.redis_cfg.port, self.redis_cfg.db)
        except Exception as e:
            logger.warning("Failed to initialize Redis client (%s). Using in-memory fallback.", e)
            self.client = None
            self.is_connected = False

    async def _ensure_ping(self) -> bool:
        if not self.client:
            return False
        try:
            await self.client.ping()
            self.is_connected = True
            return True
        except Exception:
            self.is_connected = False
            return False

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        full_key = f"{self.prefix}{key}"
        if await self._ensure_ping():
            try:
                raw = await self.client.get(full_key)
                if raw:
                    self.hits += 1
                    return json.loads(raw)
                self.misses += 1
                return None
            except Exception as e:
                logger.debug("Redis get error (%s). Falling back to memory.", e)

        # Fallback to in-memory
        res = await self.memory_fallback.get(key)
        if res is not None:
            self.hits += 1
        else:
            self.misses += 1
        return res

    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        full_key = f"{self.prefix}{key}"
        ttl = ttl_seconds if ttl_seconds is not None else self.config.ttl_seconds
        payload = json.dumps(value)

        if await self._ensure_ping():
            try:
                if ttl > 0:
                    await self.client.set(full_key, payload, ex=ttl)
                else:
                    await self.client.set(full_key, payload)
                return
            except Exception as e:
                logger.debug("Redis set error (%s). Storing in memory fallback.", e)

        # Fallback
        await self.memory_fallback.set(key, value, ttl_seconds=ttl)

    async def delete(self, key: str) -> bool:
        full_key = f"{self.prefix}{key}"
        deleted = False
        if await self._ensure_ping():
            try:
                res = await self.client.delete(full_key)
                deleted = res > 0
            except Exception:
                pass
        mem_del = await self.memory_fallback.delete(key)
        return deleted or mem_del

    async def clear(self) -> None:
        if await self._ensure_ping():
            try:
                keys = await self.client.keys(f"{self.prefix}*")
                if keys:
                    await self.client.delete(*keys)
            except Exception:
                pass
        await self.memory_fallback.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        ratio = round((self.hits / float(total)) * 100, 1) if total > 0 else 0.0
        return {
            "backend": "redis" if self.is_connected else "redis_fallback_memory",
            "redis_connected": self.is_connected,
            "host": f"{self.redis_cfg.host}:{self.redis_cfg.port}",
            "db": self.redis_cfg.db,
            "ttl_seconds": self.config.ttl_seconds,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_percent": ratio,
            "fallback_stats": self.memory_fallback.get_stats(),
        }


class GatewayCacheManager:
    """Manages query caching, cache key canonicalization, and response serialization."""

    def __init__(self, config: CacheConfig):
        self.config = config
        self.backend: BaseCache = self._create_backend()

    def _create_backend(self) -> BaseCache:
        if not self.config.enabled:
            return InMemoryCache(max_entries=10, default_ttl=0)

        if self.config.backend.lower() == "redis":
            return RedisCache(self.config)
        return InMemoryCache(
            max_entries=self.config.max_entries,
            default_ttl=self.config.ttl_seconds,
            eviction_policy=self.config.eviction_policy,
        )

    def generate_cache_key(self, query_req: GatewayQuery) -> str:
        """Generates deterministic, collision-resistant canonical cache key."""
        q_norm = query_req.query.lower().strip()
        tags_sorted = sorted([t.lower().strip() for t in query_req.tags])
        sources_sorted = sorted([s.lower().strip() for s in (query_req.sources or [])])

        raw_key = (
            f"q={q_norm}|"
            f"tags={','.join(tags_sorted)}|"
            f"sources={','.join(sources_sorted)}|"
            f"page={query_req.page}|"
            f"page_size={query_req.page_size}|"
            f"min_score={query_req.min_score}"
        )
        h = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        # Friendly preview prefix for debugging
        preview = "".join(c if c.isalnum() else "_" for c in q_norm[:16])
        return f"{preview}_{h}"

    async def get_cached_response(self, query_req: GatewayQuery) -> Optional[GatewayResponse]:
        if not self.config.enabled:
            return None

        key = self.generate_cache_key(query_req)
        raw_val = await self.backend.get(key)
        if not raw_val:
            return None

        try:
            resp = GatewayResponse(**raw_val)
            resp.cached = True
            stats = self.backend.get_stats()
            resp.cache_backend = stats.get("backend", "cache")
            return resp
        except Exception as e:
            logger.warning("Failed to deserialize cached response: %s", e)
            return None

    async def cache_response(self, query_req: GatewayQuery, response: GatewayResponse) -> None:
        if not self.config.enabled:
            return

        key = self.generate_cache_key(query_req)
        # Store serialized dict
        data = response.model_dump()
        data["cached"] = True
        stats = self.backend.get_stats()
        data["cache_backend"] = stats.get("backend", "cache")
        await self.backend.set(key, data, ttl_seconds=self.config.ttl_seconds)

    async def clear(self) -> None:
        await self.backend.clear()

    def get_stats(self) -> Dict[str, Any]:
        if not self.config.enabled:
            return {"enabled": False, "status": "disabled"}
        stats = self.backend.get_stats()
        stats["enabled"] = True
        return stats

import asyncio
import time
import pytest
from src.cache import InMemoryCache, RedisCache, GatewayCacheManager
from src.config import CacheConfig, RedisConfig, GatewayConfig
from src.gateway import KnowledgeGateway
from src.models import GatewayQuery, GatewayResponse, GatewayKnowledgeItem


@pytest.mark.asyncio
async def test_in_memory_cache_basic_and_ttl():
    cache = InMemoryCache(max_entries=5, default_ttl=2, eviction_policy="lru")

    await cache.set("k1", {"msg": "hello"}, ttl_seconds=1)
    val = await cache.get("k1")
    assert val == {"msg": "hello"}

    # Wait for TTL expiration
    await asyncio.sleep(1.1)
    expired_val = await cache.get("k1")
    assert expired_val is None


@pytest.mark.asyncio
async def test_in_memory_cache_lru_eviction():
    cache = InMemoryCache(max_entries=3, default_ttl=300, eviction_policy="lru")

    await cache.set("k1", {"val": 1})
    await cache.set("k2", {"val": 2})
    await cache.set("k3", {"val": 3})

    # Access k1 to make k2 the least recently used
    await cache.get("k1")

    # Add 4th item, should evict k2
    await cache.set("k4", {"val": 4})

    assert await cache.get("k1") is not None
    assert await cache.get("k2") is None  # evicted
    assert await cache.get("k3") is not None
    assert await cache.get("k4") is not None


@pytest.mark.asyncio
async def test_in_memory_cache_lfu_eviction():
    cache = InMemoryCache(max_entries=3, default_ttl=300, eviction_policy="lfu")

    await cache.set("k1", {"val": 1})
    await cache.set("k2", {"val": 2})
    await cache.set("k3", {"val": 3})

    # Access k1 multiple times, k3 once, k2 zero times
    await cache.get("k1")
    await cache.get("k1")
    await cache.get("k3")

    # Adding k4 should evict k2 (least frequently used)
    await cache.set("k4", {"val": 4})

    assert await cache.get("k1") is not None
    assert await cache.get("k2") is None  # evicted
    assert await cache.get("k3") is not None
    assert await cache.get("k4") is not None


@pytest.mark.asyncio
async def test_redis_cache_fallback_behavior():
    # Connecting to non-existent port should seamlessly fallback to memory cache
    cfg = CacheConfig(
        enabled=True,
        backend="redis",
        ttl_seconds=60,
        max_entries=100,
        redis=RedisConfig(host="localhost", port=59999, timeout_seconds=0.2),
    )
    rc = RedisCache(cfg)
    assert rc.is_connected is False

    await rc.set("fallback_key", {"status": "ok"})
    res = await rc.get("fallback_key")
    assert res == {"status": "ok"}
    stats = rc.get_stats()
    assert "fallback" in stats["backend"]


@pytest.mark.asyncio
async def test_gateway_caching_end_to_end():
    config = GatewayConfig()
    config.cache.enabled = True
    config.cache.backend = "memory"
    config.cache.ttl_seconds = 60

    gw = KnowledgeGateway(config)
    await gw.cache.clear()

    query = GatewayQuery(
        query="Which services depend on vault secrets engine?",
        sources=["okf"],
        tags=["vault"],
        page=1,
        page_size=3,
        min_score=0.10,
    )

    # First request: Cache MISS (must run parallel retrieval & ONNX re-ranking)
    res1 = await gw.query(query)
    assert res1.cached is False
    assert len(res1.items) > 0
    t1_latency = res1.latency_ms

    # Second request: Cache HIT (must be served instantly from cache)
    res2 = await gw.query(query)
    assert res2.cached is True
    assert res2.cache_backend in ["in_memory", "memory", "redis", "redis_fallback_memory"]
    assert len(res2.items) == len(res1.items)
    assert [i.id for i in res2.items] == [i.id for i in res1.items]
    # Cache hit latency is typically sub-millisecond
    assert res2.latency_ms < t1_latency or res2.latency_ms < 5.0

    # Cache clear test
    await gw.cache.clear()
    res3 = await gw.query(query)
    assert res3.cached is False

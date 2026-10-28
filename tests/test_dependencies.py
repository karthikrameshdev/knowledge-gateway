"""Real HTTP embedding transport and real local databases; opt-in, never call paid providers."""
import os
import uuid
import asyncio
import pytest
from src.config import load_config, RAGConfig, EmbeddingConfig, CacheConfig, RedisConfig
from src.models import GatewayQuery
from src.gateway import KnowledgeGateway, GatewayUnavailable
from src.cache import RedisCache
from src.connectors.rag_connector import RAGConnector


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('KG_RUN_INTEGRATION') != '1', reason='Run ./test.sh --integration')
async def test_real_redis_ttl_isolation_and_namespaced_clear():
    import redis.asyncio as redis
    namespace = 'kg:test:' + uuid.uuid4().hex + ':'
    cache = RedisCache(CacheConfig(backend='redis', redis=RedisConfig(port=6389, key_prefix=namespace)))
    client = redis.Redis(port=6389, decode_responses=True)
    try:
        await client.set('kg:other:sentinel', 'keep', ex=20)
        await cache.set('one', {'result': 1}, ttl_seconds=1)
        assert await cache.get('one') == {'result': 1}
        assert cache.is_connected
        await asyncio.sleep(1.1)
        assert await cache.get('one') is None
        await cache.set('two', {'result': 2})
        await cache.clear()
        assert await cache.get('two') is None
        assert await client.get('kg:other:sentinel') == 'keep'
    finally:
        await client.delete('kg:other:sentinel')
        await cache.aclose()
        await client.aclose()


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('KG_RUN_INTEGRATION') != '1', reason='Run ./test.sh --integration')
async def test_real_qdrant_retrieval():
    connector = RAGConnector(RAGConfig(port=6339, collection='test_' + uuid.uuid4().hex, embedding=EmbeddingConfig(provider='deterministic')))
    try:
        await connector.run_blocking(connector.index_seed_documents, [{'id': 'vault', 'title': 'Vault encryption', 'content': 'Vault protects secrets'}])
        results = await connector.search('Vault secrets', [])
        assert results[0].id == 'vault'
        assert (await connector.health_check())['status'] == 'healthy'
    finally:
        if connector.client:
            await connector.run_blocking(connector.client.delete_collection, connector.config.collection)
        await connector.aclose()


SIMULATION = os.environ.get('KG_SIMULATION_URL')
@pytest.mark.simulation
@pytest.mark.skipif(not SIMULATION, reason='Start the committed Postman simulation and set KG_SIMULATION_URL')
@pytest.mark.parametrize('route,query,success', [
    ('embeddings', 'vault secrets', True),
    ('embeddings', 'malformed-vector-fixture', False),
    ('json-error', 'vault secrets', False),
    ('html-error', 'vault secrets', False),
    ('timeout', 'vault secrets', False),
])
async def test_gateway_with_real_embedding_http_transport(route, query, success):
    config = load_config('config.demo.yaml')
    config.rag.embedding = EmbeddingConfig(provider='openai', openai_url=SIMULATION + '/' + route + '/v1', dimension=8, timeout_seconds=0.1)
    config.gateway.demo_mode = False
    gw = KnowledgeGateway(config)
    rag = gw.connectors['rag']
    # The seed uses the normal API member; only the query's endpoint is failed.
    rag.embedder.openai_url = SIMULATION + '/embeddings/v1'
    await rag.run_blocking(rag.index_seed_documents, [{'id': 'vault', 'title': 'Vault', 'content': 'Vault secrets'}])
    rag.embedder.openai_url = SIMULATION + '/' + route + '/v1'
    try:
        request = GatewayQuery(query=query, sources=['rag'])
        if success:
            result = await gw.query(request)
            assert result.items and not result.degraded
        else:
            with pytest.raises(GatewayUnavailable):
                await gw.query(request)
            assert await gw.cache.get_cached_response(request) is None
    finally:
        await gw.aclose()

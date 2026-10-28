import asyncio
import json
import time
from pathlib import Path
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient
from src.config import GatewayConfig, SecurityConfig, CacheConfig, load_config
from src.server import create_app
from src.gateway import KnowledgeGateway, GatewayUnavailable, GatewayBusy
from src.models import GatewayQuery, GatewayKnowledgeItem
from src.connectors.base import BaseConnector
from src.cache import GatewayCacheManager, InMemoryCache
from src.onnx_engine import ONNXConsolidatorEngine


@pytest.mark.parametrize('payload', [
    {'query': ''}, {'query': '   '}, {'query': 'x' * 8001},
    {'query': 'hello', 'sources': ['typo']}, {'query': 'hello', 'sources': []},
    {'query': 'hello', 'tags': ['']}, {'query': 'hello', 'tags': ['a' * 129]},
    {'query': 'hello', 'page': 0}, {'query': 'hello', 'page_size': 51},
    {'query': 'hello', 'min_score': float('nan')}, {'query': 'hello', 'min_score': float('inf')},
    {'query': 'hello', 'unexpected': True},
])
def test_invalid_requests_rejected(payload):
    with pytest.raises(ValidationError):
        GatewayQuery(**payload)


def test_config_expands_secrets_after_yaml_parse(tmp_path, monkeypatch):
    secret = 'quote: "\\npassword: injected'
    monkeypatch.setenv('EXAMPLE_SECRET', secret)
    file = tmp_path / 'config.yaml'
    file.write_text('security:\n  api_key: "${EXAMPLE_SECRET}"\n')
    assert load_config(str(file)).security.api_key == secret
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / 'missing.yaml'))


def test_secure_api_contract_and_redaction():
    config = load_config('config.demo.yaml')
    config.security.api_key = 'only-the-test-key'
    config.cache.redis.password = 'redis-private-password'
    config.sql.password = 'sql-private-password'
    config.rag.embedding.api_key = 'embedding-private-key'
    with TestClient(create_app(config)) as client:
        for route in ['/api/v1/activity', '/api/v1/config', '/api/v1/sources/status', '/api/v1/tail/stream']:
            assert client.get(route).status_code == 401
        assert client.post('/api/v1/cache/clear').status_code == 401
        headers = {'X-API-Key': config.security.api_key}
        sanitized = client.get('/api/v1/config', headers=headers)
        for secret in [config.security.api_key, config.sql.password, config.cache.redis.password, config.rag.embedding.api_key]:
            assert secret not in sanitized.text
        assert client.get('/api/v1/config', headers={'Authorization': 'Bearer only-the-test-key'}).status_code == 200
        result = client.post('/api/v1/query', json={'query': 'vault', 'sources': ['okf']}, headers=headers)
        assert result.status_code == 200
        assert result.json()['request_id'] == result.headers['X-Request-ID']
        assert result.headers['Cache-Control'] == 'no-store'
        assert client.post('/api/v1/query', content=b'x' * 65537, headers=headers).status_code == 413
        assert client.get('/health', headers={'Host': 'hostile.example'}).status_code == 400
        preflight = client.options('/api/v1/query', headers={'Origin': 'https://other.example', 'Access-Control-Request-Method': 'POST'})
        assert 'Access-Control-Allow-Origin' not in preflight.headers


def test_configured_pagination_and_activity_filter():
    config = load_config('config.demo.yaml')
    config.gateway.pagination.default_page_size = 2
    config.gateway.pagination.max_page_size = 3
    with TestClient(create_app(config)) as client:
        assert client.post('/api/v1/query', json={'query': 'vault', 'sources': ['okf']}).json()['page_size'] == 2
        assert client.post('/api/v1/query', json={'query': 'vault', 'page_size': 4}).status_code == 422
        assert client.get('/api/v1/activity?query=never-searched-this').json()['total'] == 0
        assert client.get('/ready').status_code == 200


class ProbeConnector(BaseConnector):
    def __init__(self, name='okf', delay=0, fail=False):
        super().__init__(name, name)
        self.delay, self.fail, self.calls = delay, fail, 0

    async def search(self, query, tags, top_k=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError('private upstream error must not escape')
        return [GatewayKnowledgeItem(id=self.source_type, source_type=self.source_type, title='Vault policy', content='Vault policy document', snippet='Vault')]

    async def health_check(self):
        return {'status': 'healthy'}


def probe_gateway():
    config = GatewayConfig()
    config.gateway.onnx_engine.enabled = False
    config.gateway.source_timeout_seconds = 0.04
    return KnowledgeGateway(config)


@pytest.mark.asyncio
async def test_parallel_timeout_keeps_healthy_results_and_does_not_cache_partial():
    gw = probe_gateway()
    healthy, slow = ProbeConnector(), ProbeConnector('sql', delay=0.2)
    gw.connectors = {'okf': healthy, 'sql': slow}
    start = time.perf_counter()
    result = await gw.query(GatewayQuery(query='vault'))
    assert time.perf_counter() - start < 0.15
    assert result.degraded
    assert result.sources_searched['sql'].status == 'timeout'
    assert result.sources_searched['sql'].latency_ms >= 30
    assert result.items
    await gw.query(GatewayQuery(query='vault'))
    assert healthy.calls == 2
    await gw.aclose()


@pytest.mark.asyncio
async def test_all_sources_failed_raises_instead_of_false_empty_success():
    gw = probe_gateway()
    gw.connectors = {'okf': ProbeConnector(fail=True)}
    with pytest.raises(GatewayUnavailable):
        await gw.query(GatewayQuery(query='vault'))
    await gw.aclose()


@pytest.mark.asyncio
async def test_identical_concurrent_queries_share_work_with_distinct_request_ids():
    gw = probe_gateway()
    conn = ProbeConnector(delay=0.015)
    gw.connectors = {'okf': conn}
    responses = await asyncio.gather(*(gw.query(GatewayQuery(query='vault')) for _ in range(20)))
    assert conn.calls == 1
    assert len({r.request_id for r in responses}) == 20
    responses[0].items[0].title = 'mutated'
    hit = await gw.query(GatewayQuery(query='vault'))
    assert hit.cached
    assert hit.items[0].title == 'Vault policy'
    await gw.aclose()


@pytest.mark.asyncio
async def test_clear_during_inflight_query_prevents_stale_repopulation():
    gw = probe_gateway()
    conn = ProbeConnector(delay=0.02)
    gw.connectors = {'okf': conn}
    pending = asyncio.create_task(gw.query(GatewayQuery(query='vault')))
    await asyncio.sleep(0.005)
    await gw.cache.clear()
    await pending
    response = await gw.query(GatewayQuery(query='vault'))
    assert not response.cached
    assert conn.calls == 2
    await gw.aclose()


@pytest.mark.asyncio
async def test_synchronous_connector_does_not_block_event_loop():
    conn = ProbeConnector()
    task = asyncio.create_task(conn.run_blocking(time.sleep, 0.05))
    await asyncio.sleep(0.005)
    assert not task.done()
    await task
    await conn.aclose()


@pytest.mark.asyncio
async def test_worker_limit_survives_cancelled_http_waiters():
    conn = ProbeConnector()
    tasks = [asyncio.create_task(conn.run_blocking(time.sleep, 0.05)) for _ in range(4)]
    await asyncio.sleep(0.005)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert conn._workers.locked()
    await conn.aclose()
    assert not conn._workers.locked()


def test_canonical_keys_have_no_delimiter_collision_or_query_text():
    manager = GatewayCacheManager(CacheConfig())
    one = manager.generate_cache_key(GatewayQuery(query='vault', tags=['a,b']))
    two = manager.generate_cache_key(GatewayQuery(query='vault', tags=['a', 'b']))
    assert one != two
    assert len(one) == 64
    assert 'vault' not in one
    assert manager.generate_cache_key(GatewayQuery(query='Vault')) != manager.generate_cache_key(GatewayQuery(query='vault'))


@pytest.mark.asyncio
async def test_memory_cache_isolates_mutable_values_and_fifo_eviction():
    cache = InMemoryCache(max_entries=2, eviction_policy='fifo')
    source = {'nested': [1]}
    await cache.set('a', source)
    source['nested'].append(2)
    value = await cache.get('a')
    assert value == {'nested': [1]}
    value['nested'].append(3)
    assert await cache.get('a') == {'nested': [1]}
    await cache.set('b', {})
    await cache.get('a')
    await cache.set('c', {})
    assert await cache.get('a') is None


def test_tied_scores_have_stable_source_and_id_order():
    from src.config import ONNXEngineConfig
    engine = ONNXConsolidatorEngine(ONNXEngineConfig(enabled=False))
    items = [GatewayKnowledgeItem(id=k, source_type='okf', title='same', content='same', snippet='same') for k in ['z', 'a']]
    first, _ = engine.consolidate_and_rerank('same', [], items)
    second, _ = engine.consolidate_and_rerank('same', [], list(reversed(items)))
    assert [i.id for i in first] == [i.id for i in second] == ['a', 'z']
    assert items[0].score == 0


@pytest.mark.asyncio
async def test_filesystem_skips_symlinks_hidden_files_and_oversized_files(tmp_path):
    from src.config import FilesystemConfig, FilesystemDirectoryConfig
    from src.connectors.fs_connector import FilesystemConnector
    root = tmp_path / 'docs'
    root.mkdir()
    (root / 'good.md').write_text('# Vault\nVault secrets')
    (root / '.hidden.md').write_text('vault private')
    (root / 'large.md').write_text('vault ' * 100)
    secret = tmp_path / 'private.md'
    secret.write_text('vault confidential')
    (root / 'link.md').symlink_to(secret)
    conn = FilesystemConnector(FilesystemConfig(directories=[FilesystemDirectoryConfig(path=str(root))], max_file_bytes=100))
    found = await conn.search('vault', [])
    assert len(found) == 1
    assert found[0].title == 'Vault'
    await conn.aclose()


@pytest.mark.asyncio
async def test_okf_relations_are_generic_and_refresh_after_updates(tmp_path):
    from src.config import OKFConfig
    from src.connectors.okf_connector import OKFConnector
    (tmp_path / 'root.md').write_text('---\nid: custom-ledger\ntitle: Custom Ledger\n---\nLedger system')
    (tmp_path / 'child.md').write_text('---\nid: billing\ntitle: Billing\nrelations:\n  depends_on: [custom-ledger]\n---\nBilling service')
    conn = OKFConnector(OKFConfig(root_dir=str(tmp_path), refresh_interval_seconds=0))
    results = await conn.search('Which services depend on custom-ledger?', [])
    assert {'custom-ledger', 'billing'} <= {r.id for r in results}
    (tmp_path / 'root.md').write_text('---\nid: custom-ledger\ntitle: Updated Ledger\n---\nLedger system')
    results = await conn.search('custom-ledger', [])
    assert any(r.title == 'Updated Ledger' for r in results)
    await conn.aclose()

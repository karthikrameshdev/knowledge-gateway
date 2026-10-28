import asyncio
import math
import time
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional
from .config import GatewayConfig, load_config
from .models import GatewayQuery, GatewayResponse, SourceRetrievalStats, ActivityLogEntry
from .logger import ActivityLogger
from .onnx_engine import ONNXConsolidatorEngine
from .cache import GatewayCacheManager
from .connectors.rag_connector import RAGConnector
from .connectors.okf_connector import OKFConnector
from .connectors.fs_connector import FilesystemConnector
from .connectors.git_connector import GitConnector
from .connectors.sql_connector import SQLConnector


class GatewayUnavailable(RuntimeError):
    pass


class GatewayBusy(RuntimeError):
    pass


class KnowledgeGateway:
    """Bounded parallel retrieval; failures are explicit and never cached as complete answers."""

    def __init__(self, config: Optional[GatewayConfig] = None, logger_instance: Optional[ActivityLogger] = None):
        self.config = config or load_config()
        self.logger = logger_instance or ActivityLogger()
        self.onnx_engine = ONNXConsolidatorEngine(self.config.gateway.onnx_engine)
        scope = self.config.model_dump(exclude={'security', 'cache'})
        import json
        self.cache = GatewayCacheManager(self.config.cache, scope=hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest())
        self.connectors = {
            'rag': RAGConnector(self.config.rag), 'okf': OKFConnector(self.config.okf),
            'filesystem': FilesystemConnector(self.config.filesystem),
            'git': GitConnector(self.config.git), 'sql': SQLConnector(self.config.sql),
        }
        self._slots = asyncio.Semaphore(self.config.gateway.max_concurrent_queries)
        self._inflight = {}

    async def query(self, query_req: GatewayQuery, client_ip='127.0.0.1', request_id=None) -> GatewayResponse:
        start = time.perf_counter()
        request_id = request_id or 'req_' + uuid.uuid4().hex
        active = {key: conn for key, conn in self.connectors.items() if conn.enabled and (query_req.sources is None or key in query_req.sources)}
        if not active:
            raise ValueError('No enabled knowledge sources selected')
        if query_req.page_size > self.config.gateway.pagination.max_page_size:
            raise ValueError('page_size exceeds the configured maximum')
        response = await self.cache.get_cached_response(query_req)
        traces = []
        if response is None:
            generation = self.cache.generation
            key = f'{generation}:' + self.cache.generate_cache_key(query_req)
            task = self._inflight.get(key)
            if task is None:
                if len(self._inflight) >= self.config.gateway.max_concurrent_queries * 4:
                    raise GatewayBusy('Query capacity exceeded')
                task = asyncio.create_task(self._execute(query_req, active, generation))
                self._inflight[key] = task
                def done(job):
                    if self._inflight.get(key) is job:
                        self._inflight.pop(key, None)
                    if not job.cancelled():
                        job.exception()
                task.add_done_callback(done)
            response, traces = await asyncio.shield(task)
            response = response.model_copy(deep=True)
        response.request_id = request_id
        response.latency_ms = round((time.perf_counter() - start) * 1000, 3)
        breakdown = {k: stat.model_dump() for k, stat in response.sources_searched.items()}
        if response.cached:
            breakdown['cache'] = {'status': 'hit', 'backend': response.cache_backend}
        self.logger.record(ActivityLogEntry(
            request_id=request_id, timestamp=datetime.now(timezone.utc).isoformat(), client_ip=client_ip,
            latency_ms=response.latency_ms, query=query_req.query, tags=query_req.tags,
            page=query_req.page, page_size=query_req.page_size, sources_attempted=list(active),
            source_breakdown=breakdown,
            total_raw_candidates=sum(s.count for s in response.sources_searched.values()),
            total_consolidated_items=response.total_results, items_returned_count=len(response.items),
            top_score=response.items[0].score if response.items else 0,
            candidates_reranking=traces, cached=response.cached, cache_backend=response.cache_backend,
            response_payload=response.model_dump(),
        ))
        return response

    async def _execute(self, query_req, active, generation):
        try:
            await asyncio.wait_for(self._slots.acquire(), self.config.gateway.queue_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise GatewayBusy('Query capacity exceeded; retry later') from exc
        try:
            results = await asyncio.gather(*(self._search(key, conn, query_req) for key, conn in active.items()))
            candidates, stats = [], {}
            for key, items, stat in results:
                candidates.extend(items)
                stats[key] = stat
            if all(s.status in ('error', 'timeout') for s in stats.values()):
                raise GatewayUnavailable('All selected knowledge sources are unavailable')
            ranked, traces = await asyncio.to_thread(
                self.onnx_engine.consolidate_and_rerank, query_req.query, query_req.tags, candidates, query_req.min_score,
            )
            total = len(ranked)
            pages = max(1, math.ceil(total / query_req.page_size))
            offset = (query_req.page - 1) * query_req.page_size
            response = GatewayResponse(
                query=query_req.query, tags=query_req.tags, page=query_req.page, page_size=query_req.page_size,
                total_results=total, total_pages=pages, has_next=query_req.page < pages,
                has_previous=query_req.page > 1, latency_ms=0, sources_searched=stats,
                items=ranked[offset:offset + query_req.page_size],
                degraded=any(s.status in ('error', 'timeout') for s in stats.values()),
                ranking_mode='onnx_feature_model' if self.onnx_engine.is_onnx_active else 'heuristic',
                cache_backend=self.cache.get_stats().get('backend'),
            )
            await self.cache.cache_response(query_req, response, generation=generation)
            return response, traces
        finally:
            self._slots.release()

    async def _search(self, key, connector, query):
        start = time.perf_counter()
        try:
            items = await asyncio.wait_for(connector.search(query.query, query.tags), self.config.gateway.source_timeout_seconds)
            status, error = ('ok' if items else 'empty'), None
        except asyncio.TimeoutError:
            items, status, error = [], 'timeout', 'source_timeout'
        except Exception:
            items, status, error = [], 'error', 'source_unavailable'
        return key, items, SourceRetrievalStats(
            source_type=key, count=len(items), status=status, error=error,
            latency_ms=round((time.perf_counter() - start) * 1000, 3),
        )

    async def get_all_sources_status(self):
        async def check(key, conn):
            try:
                return key, await asyncio.wait_for(conn.health_check(), self.config.gateway.source_timeout_seconds)
            except asyncio.TimeoutError:
                return key, {'status': 'timeout', 'error': 'source_timeout'}
            except Exception:
                return key, {'status': 'error', 'error': 'source_unavailable'}
        statuses = dict(await asyncio.gather(*(check(k, c) for k, c in self.connectors.items())))
        statuses['cache'] = self.cache.get_stats()
        statuses['onnx_engine'] = {'status': 'active' if self.onnx_engine.is_onnx_active else 'fallback_heuristic',
                                   'model_path': self.config.gateway.onnx_engine.model_path,
                                   'score_threshold': self.config.gateway.onnx_engine.score_threshold}
        return statuses

    async def aclose(self):
        if self._inflight:
            await asyncio.gather(*self._inflight.values(), return_exceptions=True)
        await asyncio.gather(*(c.aclose() for c in self.connectors.values()))
        await self.cache.aclose()

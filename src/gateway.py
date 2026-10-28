import asyncio
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from .config import GatewayConfig, load_config
from .models import (
    GatewayQuery,
    GatewayResponse,
    GatewayKnowledgeItem,
    SourceRetrievalStats,
    ActivityLogEntry,
)
from .logger import ActivityLogger, global_activity_logger
from .onnx_engine import ONNXConsolidatorEngine
from .connectors.base import BaseConnector
from .connectors.rag_connector import RAGConnector
from .connectors.okf_connector import OKFConnector
from .connectors.fs_connector import FilesystemConnector
from .connectors.git_connector import GitConnector
from .connectors.sql_connector import SQLConnector


class KnowledgeGateway:
    """Enterprise Knowledge Gateway consolidating heterogeneous sources via ONNX neural re-ranking."""

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        logger_instance: Optional[ActivityLogger] = None,
    ):
        self.config = config or load_config()
        self.logger = logger_instance or global_activity_logger
        self.onnx_engine = ONNXConsolidatorEngine(self.config.gateway.onnx_engine)
        self.connectors: Dict[str, BaseConnector] = {}
        self._init_connectors()

    def _init_connectors(self):
        # 1. RAG Connector
        self.connectors["rag"] = RAGConnector(self.config.rag)
        # 2. OKF Connector
        self.connectors["okf"] = OKFConnector(self.config.okf)
        # 3. Filesystem Connector
        self.connectors["filesystem"] = FilesystemConnector(self.config.filesystem)
        # 4. Git Connector
        self.connectors["git"] = GitConnector(self.config.git)
        # 5. SQL PostgreSQL Connector
        self.connectors["sql"] = SQLConnector(self.config.sql)

    async def query(
        self,
        query_req: GatewayQuery,
        client_ip: str = "127.0.0.1",
    ) -> GatewayResponse:
        """Executes unified, parallel knowledge retrieval across configured sources."""
        start_ns = time.perf_counter_ns()
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Determine which connectors to query
        requested_sources = query_req.sources
        active_connectors: Dict[str, BaseConnector] = {}
        for key, conn in self.connectors.items():
            if not conn.enabled:
                continue
            if requested_sources and key not in requested_sources:
                continue
            active_connectors[key] = conn

        # Dispatch parallel queries
        tasks = []
        source_keys = list(active_connectors.keys())
        for k in source_keys:
            tasks.append(self._timed_connector_search(active_connectors[k], query_req.query, query_req.tags))

        results_with_stats = await asyncio.gather(*tasks, return_exceptions=True)

        raw_candidates: List[GatewayKnowledgeItem] = []
        sources_searched_stats: Dict[str, SourceRetrievalStats] = {}
        source_breakdown_detail: Dict[str, Dict[str, Any]] = {}

        for k, res in zip(source_keys, results_with_stats):
            if isinstance(res, Exception):
                sources_searched_stats[k] = SourceRetrievalStats(
                    source_type=k,
                    count=0,
                    latency_ms=0.0,
                    status="error",
                    error=str(res),
                )
                source_breakdown_detail[k] = {
                    "status": "error",
                    "count": 0,
                    "latency_ms": 0.0,
                    "error": str(res),
                }
            else:
                items, latency_ms = res
                raw_candidates.extend(items)
                stat = SourceRetrievalStats(
                    source_type=k,
                    count=len(items),
                    latency_ms=latency_ms,
                    status="ok" if items else "empty",
                )
                sources_searched_stats[k] = stat
                source_breakdown_detail[k] = {
                    "status": stat.status,
                    "count": len(items),
                    "latency_ms": latency_ms,
                    "item_ids": [it.id for it in items],
                }

        # Consolidate and re-rank via ONNX Engine
        consolidated_items, candidate_traces = self.onnx_engine.consolidate_and_rerank(
            query=query_req.query,
            tags=query_req.tags,
            candidates=raw_candidates,
            min_score=query_req.min_score,
        )

        # Pagination calculations
        page = query_req.page
        page_size = query_req.page_size
        total_results = len(consolidated_items)
        total_pages = max(1, math.ceil(total_results / float(page_size)))
        has_next = page < total_pages
        has_previous = page > 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = consolidated_items[start_idx:end_idx]

        total_latency_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)
        top_score = consolidated_items[0].score if consolidated_items else 0.0

        response = GatewayResponse(
            query=query_req.query,
            tags=query_req.tags,
            page=page,
            page_size=page_size,
            total_results=total_results,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
            latency_ms=total_latency_ms,
            sources_searched=sources_searched_stats,
            items=paginated_items,
        )

        # Record activity entry for live tailing and auditing
        activity_entry = ActivityLogEntry(
            request_id=request_id,
            timestamp=timestamp,
            client_ip=client_ip,
            method="POST",
            path="/api/v1/query",
            status_code=200,
            latency_ms=total_latency_ms,
            query=query_req.query,
            tags=query_req.tags,
            page=page,
            page_size=page_size,
            sources_attempted=source_keys,
            source_breakdown=source_breakdown_detail,
            total_raw_candidates=len(raw_candidates),
            total_consolidated_items=total_results,
            items_returned_count=len(paginated_items),
            top_score=top_score,
            candidates_reranking=candidate_traces,
            response_payload=response.model_dump(),
        )
        self.logger.record(activity_entry)

        return response

    async def _timed_connector_search(
        self,
        connector: BaseConnector,
        query: str,
        tags: List[str],
    ) -> Tuple[List[GatewayKnowledgeItem], float]:
        t0 = time.perf_counter_ns()
        try:
            items = await connector.search(query, tags)
            latency_ms = round((time.perf_counter_ns() - t0) / 1_000_000.0, 3)
            return items, latency_ms
        except Exception as e:
            latency_ms = round((time.perf_counter_ns() - t0) / 1_000_000.0, 3)
            raise e

    async def get_all_sources_status(self) -> Dict[str, Any]:
        """Runs health checks on all configured connectors and ONNX engine."""
        statuses = {}
        for k, conn in self.connectors.items():
            try:
                statuses[k] = await conn.health_check()
            except Exception as e:
                statuses[k] = {"status": "error", "error": str(e)}

        statuses["onnx_engine"] = {
            "status": "active" if self.onnx_engine.is_onnx_active else "fallback_heuristic",
            "model_path": self.config.gateway.onnx_engine.model_path,
            "score_threshold": self.config.gateway.onnx_engine.score_threshold,
        }
        return statuses

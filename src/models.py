from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class GatewayQuery(BaseModel):
    query: str
    tags: List[str] = Field(default_factory=list)
    sources: Optional[List[str]] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.15, ge=0.0, le=1.0)


class GatewayKnowledgeItem(BaseModel):
    id: str
    source_type: str  # "rag", "okf", "filesystem", "git", "sql"
    title: str
    content: str
    snippet: str
    score: float = 0.0
    raw_score: float = 0.0
    onnx_score: float = 0.0
    provenance: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceRetrievalStats(BaseModel):
    source_type: str
    count: int = 0
    latency_ms: float = 0.0
    status: str = "ok"  # "ok", "error", "skipped", "empty"
    error: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class GatewayResponse(BaseModel):
    query: str
    tags: List[str] = Field(default_factory=list)
    page: int
    page_size: int
    total_results: int
    total_pages: int
    has_next: bool
    has_previous: bool
    latency_ms: float
    sources_searched: Dict[str, SourceRetrievalStats]
    items: List[GatewayKnowledgeItem]
    cached: bool = False
    cache_backend: Optional[str] = None


class ActivityCandidateTrace(BaseModel):
    id: str
    source_type: str
    title: str
    raw_score: float
    onnx_score: float
    features: Dict[str, float] = Field(default_factory=dict)
    accepted: bool = True


class ActivityLogEntry(BaseModel):
    request_id: str
    timestamp: str
    client_ip: str = "127.0.0.1"
    method: str = "POST"
    path: str = "/api/v1/query"
    status_code: int = 200
    latency_ms: float = 0.0
    query: str = ""
    tags: List[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = 5
    sources_attempted: List[str] = Field(default_factory=list)
    source_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    total_raw_candidates: int = 0
    total_consolidated_items: int = 0
    items_returned_count: int = 0
    top_score: float = 0.0
    candidates_reranking: List[ActivityCandidateTrace] = Field(default_factory=list)
    cached: bool = False
    cache_backend: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None

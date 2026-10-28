from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class GatewayQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    query: str = Field(min_length=1, max_length=8000)
    tags: List[str] = Field(default_factory=list, max_length=32)
    sources: Optional[List[Literal["rag", "okf", "filesystem", "git", "sql"]]] = Field(default=None, min_length=1, max_length=5)
    page: int = Field(default=1, ge=1, strict=True)
    page_size: int = Field(default=5, ge=1, le=50, strict=True)
    min_score: float = Field(default=0.15, ge=0.0, le=1.0, strict=True)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("query must contain non-whitespace text")
        return value

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values):
        if any(not v.strip() or len(v) > 128 for v in values):
            raise ValueError("tags must contain 1–128 characters")
        return sorted(set(v.strip().lower() for v in values))

    @field_validator("sources")
    @classmethod
    def clean_sources(cls, values):
        return sorted(set(values)) if values is not None else None


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
    request_id: str = ""
    degraded: bool = False
    ranking_mode: str = "heuristic"
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
    response_payload_truncated: bool = False
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

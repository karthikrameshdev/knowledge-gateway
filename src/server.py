import os
import logging
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Request, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config, GatewayConfig
from .models import GatewayQuery, GatewayResponse
from .gateway import KnowledgeGateway
from .logger import global_activity_logger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("GatewayServer")

from contextlib import asynccontextmanager

# Templates and static directories
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Instantiate Gateway instance
config = load_config()
gateway = KnowledgeGateway(config=config, logger_instance=global_activity_logger)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Knowledge Gateway v%s on port %s", config.gateway.version, config.gateway.port)
    # Automatically seed RAG sample points if empty
    try:
        rag_conn = gateway.connectors.get("rag")
        if rag_conn and rag_conn.enabled:
            rag_conn.index_seed_documents([
                {
                    "id": "weftkit_rag_core_arch",
                    "title": "WeftKit Desktop Native Core & IPC Bridge",
                    "content": "WeftKit desktop architecture leverages Tauri with Rust native bindings. The frontend React client invokes secure IPC commands to access system resources, native file watchers, and OS keychains.",
                    "category": "architecture",
                    "tags": ["tauri", "rust", "desktop", "architecture"],
                },
                {
                    "id": "weftkit_rag_auth_flow",
                    "title": "WeftKit OAuth PKCE Authentication Rails",
                    "content": "Desktop authentication is performed via Google Identity with loopback redirects on 127.0.0.1. Tokens are verified with Ed25519 signing keys and cached securely in the macOS Keychain.",
                    "category": "security",
                    "tags": ["auth", "google", "oauth", "pkce"],
                },
                {
                    "id": "weftkit_rag_vault_transit",
                    "title": "HashiCorp Vault Transit Engine Encryption",
                    "content": "Database credentials rotate every hour. Transit engine handles encryption-at-rest for PostgreSQL and vector embeddings without storing plain cryptographic keys on worker nodes.",
                    "category": "security",
                    "tags": ["vault", "transit", "encryption", "kms"],
                },
                {
                    "id": "weftkit_rag_pci_dss",
                    "title": "PCI-DSS Level 1 Compliance & Tokenization",
                    "content": "Cardholder payment transactions are tokenized end-to-end. Cardholder data environment (CDE) is isolated with strict zero-trust network boundaries and auditable access logs.",
                    "category": "compliance",
                    "tags": ["pci-dss", "payment", "compliance", "stripe"],
                },
                {
                    "id": "weftkit_rag_disaster_recovery",
                    "title": "Automated Multi-Region Failover Architecture",
                    "content": "Multi-region disaster recovery ensures sub-5-minute RTO and zero RPO. PostgreSQL standby read replicas are promoted automatically when health check ping fails.",
                    "category": "infrastructure",
                    "tags": ["disaster-recovery", "failover", "rto", "rpo", "postgres"],
                },
            ])
    except Exception as e:
        logger.debug("Startup RAG seeding note: %s", e)
    yield


# Initialize app
app = FastAPI(
    title="Knowledge Gateway API",
    description="Unified Enterprise AI Knowledge Gateway combining RAG, OKF, Filesystem, Git, and SQL with ONNX re-ranking.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Renders the Knowledge Gateway live tailing and query playground UI."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": config.gateway.name,
            "version": config.gateway.version,
            "onnx_active": gateway.onnx_engine.is_onnx_active,
        },
    )


@app.post("/api/v1/query", response_model=GatewayResponse)
async def query_gateway(query_req: GatewayQuery, request: Request):
    """Unified multi-source query endpoint with ONNX re-ranking and deterministic pagination."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    response = await gateway.query(query_req, client_ip=client_ip)
    return response


@app.get("/api/v1/activity")
async def get_activity_log(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    query: Optional[str] = None,
    source: Optional[str] = None,
):
    """Returns recent requests, latency profiles, and source breakdowns."""
    entries = global_activity_logger.get_entries(
        limit=limit,
        offset=offset,
        query_filter=query,
        source_filter=source,
    )
    return {
        "total": global_activity_logger.get_total_count(),
        "limit": limit,
        "offset": offset,
        "entries": entries,
    }


@app.get("/api/v1/activity/{request_id}")
async def get_activity_detail(request_id: str):
    """Returns full inspection breakdown for a single request:

    sources queried, per-source items, ONNX feature vectors, and payload.
    """
    entry = global_activity_logger.get_entry_by_id(request_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Request ID not found in activity log.")
    return entry


@app.get("/api/v1/tail/stream")
async def stream_live_tail():
    """Server-Sent Events (SSE) streaming live requests, latencies, and responses."""
    return StreamingResponse(
        global_activity_logger.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/sources/status")
async def get_sources_status():
    """Returns status and connection metrics for all connectors and the ONNX engine."""
    return await gateway.get_all_sources_status()


@app.get("/api/v1/config")
async def get_sanitized_config():
    """Returns the sanitized configuration."""
    data = config.model_dump()
    # Mask secrets
    if "rag" in data and "embedding" in data["rag"]:
        key = data["rag"]["embedding"].get("api_key")
        if key:
            data["rag"]["embedding"]["api_key"] = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
    if "sql" in data:
        pwd = data["sql"].get("password")
        if pwd:
            data["sql"]["password"] = "***"
    return data


@app.get("/health")
async def health_check():
    """Service health check."""
    return {
        "status": "healthy",
        "service": "knowledge-gateway",
        "version": config.gateway.version,
        "onnx_model_active": gateway.onnx_engine.is_onnx_active,
    }

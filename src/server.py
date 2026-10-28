import asyncio
import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import load_config, GatewayConfig
from .models import GatewayQuery, GatewayResponse, ActivityLogEntry
from .gateway import KnowledgeGateway, GatewayBusy, GatewayUnavailable

logger = logging.getLogger('GatewayServer')
BASE_DIR = Path(__file__).resolve().parent


class AccessMiddleware:
    """Protect data APIs, bound JSON bodies and attach correlation/security headers."""
    def __init__(self, app, api_key=''):
        self.app, self.api_key = app, api_key

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        rid = 'req_' + uuid.uuid4().hex
        scope.setdefault('state', {})['request_id'] = rid
        headers = dict(scope['headers'])
        sensitive = scope['path'].startswith('/api/')
        if sensitive and scope['method'] != 'OPTIONS' and self.api_key:
            token = headers.get(b'x-api-key', b'')
            auth = headers.get(b'authorization', b'')
            if auth.lower().startswith(b'bearer '):
                token = auth[7:]
            if not hmac.compare_digest(token, self.api_key.encode()):
                return await JSONResponse({'detail': 'Valid API key required'}, status_code=401)(scope, receive, send)
        if sensitive and scope['method'] in ('POST', 'PUT', 'PATCH'):
            body = bytearray()
            more = True
            while more:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > 65536:
                    return await JSONResponse({'detail': 'Request body exceeds 64 KiB'}, status_code=413)(scope, receive, send)
                more = message.get('more_body', False)
            original_receive = receive
            delivered = False
            async def receive_body():
                nonlocal delivered
                if delivered:
                    return await original_receive()
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            receive = receive_body
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                extra = [(b'x-request-id', rid.encode()), (b'x-content-type-options', b'nosniff'),
                         (b'referrer-policy', b'no-referrer')]
                if sensitive:
                    extra.append((b'cache-control', b'no-store'))
                message['headers'] = list(message.get('headers', [])) + extra
            await send(message)
        await self.app(scope, receive, secure_send)


def create_app(settings: Optional[GatewayConfig] = None):
    settings = settings or load_config()
    service = KnowledgeGateway(settings)
    templates = Jinja2Templates(directory=str(BASE_DIR / 'web/templates'))

    @asynccontextmanager
    async def lifespan(application):
        if settings.gateway.demo_mode and settings.rag.enabled:
            if settings.rag.mode != 'memory' or settings.rag.embedding.provider != 'deterministic':
                raise ValueError('Demo seeding requires in-memory Qdrant and deterministic embeddings')
            from .demo import DEMO_DOCUMENTS
            await service.connectors['rag'].run_blocking(service.connectors['rag'].index_seed_documents, DEMO_DOCUMENTS)
        try:
            yield
        finally:
            await service.aclose()

    application = FastAPI(title='Knowledge Gateway API', version=settings.gateway.version,
                          description='Source-grounded retrieval across RAG, OKF, files, Git and PostgreSQL. Returns context, not generated answers.', lifespan=lifespan)
    application.state.gateway = service
    application.state.config = settings
    application.add_middleware(AccessMiddleware, api_key=settings.security.api_key)
    application.add_middleware(CORSMiddleware, allow_origins=settings.security.cors_origins,
                               allow_credentials=False, allow_methods=['GET', 'POST'],
                               allow_headers=['Content-Type', 'X-API-Key', 'Authorization'])
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.security.allowed_hosts)
    application.mount('/static', StaticFiles(directory=str(BASE_DIR / 'web/static')), name='static')

    def schema():
        if application.openapi_schema is None:
            result = get_openapi(title=application.title, version=application.version, routes=application.routes)
            result.setdefault('components', {})['securitySchemes'] = {'ApiKey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'}}
            for path, methods in result['paths'].items():
                if path.startswith('/api/'):
                    for operation in methods.values():
                        operation['security'] = [{'ApiKey': []}]
            application.openapi_schema = result
        return application.openapi_schema
    application.openapi = schema

    @application.get('/', response_class=HTMLResponse)
    async def index_page(request: Request):
        return templates.TemplateResponse(request=request, name='index.html', context={
            'title': settings.gateway.name, 'version': settings.gateway.version,
            'onnx_active': service.onnx_engine.is_onnx_active,
        })

    @application.post('/api/v1/query', response_model=GatewayResponse)
    async def query_gateway(query_req: GatewayQuery, request: Request):
        if 'page_size' not in query_req.model_fields_set:
            query_req.page_size = settings.gateway.pagination.default_page_size
        try:
            response = await service.query(query_req, client_ip=request.client.host if request.client else 'unknown', request_id=request.state.request_id)
            return response
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (GatewayBusy, GatewayUnavailable) as exc:
            raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from exc

    @application.get('/api/v1/activity')
    async def get_activity_log(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), query: Optional[str] = Query(None, max_length=8000), source: Optional[str] = None):
        matched = service.logger.get_entries(limit=service.logger.max_entries, query_filter=query, source_filter=source)
        return {'total': len(matched), 'limit': limit, 'offset': offset, 'entries': matched[offset:offset + limit]}

    @application.get('/api/v1/activity/{request_id}')
    async def get_activity_detail(request_id: str):
        entry = service.logger.get_entry_by_id(request_id)
        if entry is None:
            raise HTTPException(404, 'Request ID not found in activity log')
        return entry

    @application.get('/api/v1/tail/stream')
    async def stream_live_tail():
        return StreamingResponse(service.logger.subscribe(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @application.get('/api/v1/sources/status')
    async def get_sources_status():
        return await service.get_all_sources_status()

    @application.get('/api/v1/config')
    async def get_sanitized_config():
        def redact(value):
            if isinstance(value, dict):
                return {k: ('***' if k in ('password', 'api_key', 'token', 'secret') and v else redact(v)) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(v) for v in value]
            return value
        return redact(settings.model_dump())

    @application.get('/api/v1/cache/stats')
    async def get_cache_stats():
        return service.cache.get_stats()

    @application.post('/api/v1/cache/clear')
    async def clear_cache():
        try:
            await service.cache.clear()
        except RuntimeError as exc:
            raise HTTPException(503, 'Shared cache could not be invalidated; retry when Redis is available') from exc
        return {'status': 'cleared', 'message': 'Cache successfully invalidated'}

    @application.get('/health')
    async def health_check():
        return {'status': 'healthy', 'service': 'knowledge-gateway', 'version': settings.gateway.version,
                'onnx_model_active': service.onnx_engine.is_onnx_active, 'cache': service.cache.get_stats()}

    @application.get('/ready')
    async def readiness():
        statuses = await service.get_all_sources_status()
        enabled = [statuses[k].get('status') for k, c in service.connectors.items() if c.enabled]
        ready = any(s == 'healthy' for s in enabled)
        return JSONResponse({'status': 'ready' if ready else 'unavailable',
                             'degraded': any(s != 'healthy' for s in enabled)}, status_code=200 if ready else 503)

    return application


app = create_app()
config = app.state.config
gateway = app.state.gateway

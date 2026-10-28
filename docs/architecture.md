# Architecture and deployment contract

## Request lifecycle

Access middleware authenticates `/api/` requests with a constant-time shared key comparison, limits JSON bodies, and creates a request ID. Pydantic validates query/source/tag/page bounds. A configuration-scoped canonical key checks the TTL cache. On a miss, an in-process single-flight map coalesces identical requests before a bounded admission semaphore. Selected enabled connectors run concurrently, each with a deadline. Blocking library work is isolated in four worker slots per connector; cancellation does not release a still-running thread's slot. The gateway reranks, sorts by `(-score, source_type, id)`, slices the requested page, caches complete responses only, and records bounded inspection metadata.

A source deadline bounds the caller's wait, not arbitrary Python thread execution. A slow filesystem syscall cannot be forcibly cancelled. HTTP, Git subprocess, PostgreSQL connect and statement timeouts bound the usual external operations. Tune these with the workload. A partial response is `200` with `degraded: true` and per-source errors; total selected-source failure and overload are `503`. Responses that fail schema validation are `422`. Applications must inspect `degraded` and `sources_searched`, not just HTTP status.

## Storage and invalidation

Memory cache entries use monotonic expiry, copied values and a configurable entry limit. Entries over `max_value_bytes` are not cached. Redis uses a private key prefix, bounded network timeouts, failure backoff and local memory fallback. Clearing uses SCAN/UNLINK; failure to clear Redis is visible to the operator. A generation guard prevents an older query in this process from repopulating cache after a clear.

This is not a distributed snapshot protocol: another worker's already-running query can write during a cross-process clear. Use a distinct namespace on a coordinated deployment/change boundary, stop writers before strict invalidation, or disable cache where strict freshness is required. Source changes are visible on cache misses/TTL expiry or explicit invalidation. OKF refresh checks apply to uncached retrieval. No automatic watcher/webhook is shipped.

Activity is intentionally volatile and process-local: 200 recent entries and 100 buffered notifications per SSE subscriber. Oversized inspection response payloads are omitted beyond 256 KiB (`response_payload_truncated`); notifications never include document bodies. Queue overflow drops the oldest notification and REST remains the recovery path. Heartbeats run every 15 seconds. This is operational inspection, not a durable/compliance audit log. Query text, document content, paths and author metadata may be sensitive: restrict API access and add any required retention/redaction controls before production use.

## Source and model limits

The service supports five connector types. Filesystem and Git accept multiple configured locations; PostgreSQL accepts multiple tables. The RAG connector reads one configured Qdrant collection per instance. It does not implement pgvector, MySQL, arbitrary HTTP connector plugins, source-level RBAC, tenant-isolated authorization, or a generated-answer endpoint.

The local ONNX model has manually specified weights. Hashed-text features are not pretrained semantic embeddings; the recency value is a constant prior. Its score is a ranking signal, not calibrated confidence. Semantic quality needs a domain-specific evaluation set and, if desired, a trained replacement model. Synthetic demo vectors are explicitly configured and never substitute for failed production embeddings. Provider vector count, index, dimension and finite values are validated; vectors are never silently padded/truncated.

The filesystem scanner rejects hidden files and child symlinks, enforces file/byte enumeration limits, and uses sorted traversal. Configured root directories are trusted operator input. Treat the host's source directories as an explicit allowlist. Git operates on configured revisions with argument arrays, not a shell. SQL uses a bounded pool, read-only transactions, quoted table/column identifiers, literal search values and statement timeouts; the DB account should additionally have only SELECT permissions.

## Deployment

- Demo: `./run.sh`; loopback binding, synthetic in-memory vector store, memory cache, SQL disabled.
- Configured service: select `config.yaml` via `KNOWLEDGE_GATEWAY_CONFIG`; set a nonempty `KNOWLEDGE_GATEWAY_API_KEY` and source credentials through environment variables.
- YAML is parsed before environment interpolation, so quotes/newlines in secrets remain string values. Explicit missing configuration and unknown fields fail startup instead of silently opening a default configuration.
- Bind deliberately; allow only intended Host/Origin values. CORS does not allow credentials or arbitrary origins by default. HTTPS termination, identity authorization, request-rate policy and network rules belong at the deployment boundary.
- `/health` checks the process. `/ready` requires at least one healthy enabled retrieval source and reports degradation. Monitoring full source status requires authentication.
- Use one process when a complete local activity stream matters. Multiple workers have independent single-flight maps, activity buffers and cache metrics. Shared Redis only shares response data.
- Lifespan shutdown drains outstanding work and closes Redis, Qdrant, embedding HTTP clients and SQL pools. Startup never inserts demo data unless `demo_mode` is explicitly selected with deterministic in-memory RAG.

The bundled browser dashboard currently loads Tailwind and Lucide from CDNs. A restricted enterprise deployment should vendor/build those assets and apply its CSP before enabling the UI. The API can operate without the dashboard.

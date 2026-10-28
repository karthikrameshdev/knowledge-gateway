# Changelog

## 1.1.0 — 2026-10-28

Bounded connector workers/deadlines, partial-result reporting and all-source outage errors; in-process request coalescing and overload protection; canonical scoped caching, Redis backoff, bounded shared invalidation and in-flight clear protection; PostgreSQL pooling/read-only statements/identifier quoting; revision-aware shell-free Git access; generic refreshed OKF relations; bounded filesystem enumeration; embedding transport validation and explicit demo mode; protected data APIs, configuration secret masking and safe YAML interpolation; isolated application lifecycle, bounded SSE and browser error handling; pinned dependencies, OpenAPI snapshot, Docker packaging, regression/integration/HTTP simulations and reproducible local benchmark.

### Migration

Production RAG failures no longer silently switch to an in-memory database or synthetic embeddings. Query/source inputs and configuration now reject unknown fields. Empty source lists are invalid. Partial responses set `degraded` and are not cached; total source failure/overload return 503. Configurable pagination limits are enforced. Defaults bind to localhost; shared API-key protection is enabled by setting `KNOWLEDGE_GATEWAY_API_KEY`. Startup sample insertion requires the explicit `config.demo.yaml`. The unused legacy ONNX `weights` configuration was removed; custom ranking weights belong in the exported model. See the architecture document before updating a shared deployment.

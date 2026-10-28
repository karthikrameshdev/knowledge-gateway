# Validation — October 28, 2026

## Executed evidence

- Original baseline: 19 passed, 1 optional Docker test skipped; 43.32 s.
- Expanded suite: `KG_RUN_INTEGRATION=1 KG_SIMULATION_URL=http://127.0.0.1:4909 OPENROUTER_API_KEY='' .venv/bin/python -m pytest -q` — **53 passed in 4.89 s** on Python 3.13.13. One upstream Starlette TestClient/httpx deprecation warning; no failed assertions.
- Real PostgreSQL 16, Redis 7 and Qdrant 1.17.0 containers ran in the isolated `kg-validation` compose project, bound to loopback ports 5543, 6389 and 6339.
- Postman CLI 1.76.0 served the committed embedding HTTP simulation. Actual embedding POSTs reached its normal and HTML-error members; condition-injected JSON errors/timeouts were verified by the gateway's explicit all-source failure and no-cache assertions. Malformed dimensions were rejected without synthetic-vector fallback. No paid embedding endpoint was used.
- Live Uvicorn `/health` passed a Postman HTTP assertion. The browser dashboard executed a multi-source security query, returned provenance-rich results, and navigated to a distinct second page; no browser console errors were captured.
- `scripts/benchmark.py` ran against the real local HTTP server: 30 cold queries, 100 warm queries, and 20 concurrent warm requests. All returned non-degraded results. [Raw measurements](benchmark-2026-10-28.json): cold HTTP median 2.599 ms / p95 3.156 ms; warm HTTP median 1.233 ms / p95 2.211 ms; warm service median 0.080 ms / p95 0.166 ms. Sources were small OKF/filesystem fixtures, not an enterprise dataset or external database workload.

## Regression guarantees covered

Input validation, authentication and full secret redaction; host/CORS restrictions; request IDs and body limits; source isolation and timeout reporting; total outage errors; duplicate-request coalescing; invalidation during in-flight retrieval; mutable cache isolation; LRU/LFU/FIFO and TTL behavior; real Redis namespace isolation; real Qdrant lookup; live PostgreSQL search; deterministic ties/pagination; generic OKF relations and refresh; filesystem symlink/hidden/oversize exclusion; worker capacity after caller cancellation; vector response validation; ranking/provenance and activity lookup.

## Limits of the evidence

The comparison with baseline duration is not a controlled performance benchmark: tests and configuration changed. Local latency is not a production SLA. Paid embedding providers, production datasets, tenant authorization, distributed invalidation under simultaneous writers, long-duration soak behavior and durable audit delivery were not verified. The bundled ONNX feature model has not been trained or evaluated as a factual-confidence estimator. See [architecture](architecture.md) for deployment boundaries.

# Embedding dependency simulation

Created 2026-10-28 from the used subset of the public OpenAI-compatible embedding contract in `postman/contracts/embeddings.yaml`. The CLI is signed out, so an owner's published mock search was skipped; these are local contract-derived mocks.

## Purpose

Run the real gateway and real embedding HTTP client through success and dependency failure paths without provider credentials, cost, or external data transmission. Members and conditions are defined in `embedding-dependencies.sim.yaml`; Qdrant is a real embedded or Docker database, never a simulation member.

## Execution

Start from the repo root: `postman simulation run postman/simulations/embedding-dependencies/embedding-dependencies.sim.yaml --port 4909 --no-history --output ndjson`. Wait for the `listening` event, then run `KG_SIMULATION_URL=http://127.0.0.1:4909 .venv/bin/python -m pytest -q -m simulation`. Stop the simulation with SIGINT. Validation logs were kept outside Git in `/tmp/knowledge-gateway-simulation.ndjson`.

## Assumptions

- Synthetic vectors exercise dimensions and transport only, not semantic relevance (observed 2026-10-28, five passing simulation cases in `tests/test_dependencies.py`).
- Normal embeddings seed real embedded Qdrant; the query alone is switched to the failed member. Injected conditions short-circuit before the handler and need not produce normal member request events (observed 2026-10-28).

## Observations

<!-- begin:observations -->
- 2026-10-28: Normal and malformed-vector requests reached `embeddings`; the HTML-proxy failure reached `embedding-html-error`. JSON-error and latency conditions exercised the remaining members; the gateway rejected all failed/invalid embedding paths and did not cache their results. All five cases passed.
<!-- end:observations -->

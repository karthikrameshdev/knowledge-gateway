# Knowledge Gateway Protocol Specification

## Purpose
The Knowledge Gateway protocol standardizes how AI agents and LLMs access enterprise knowledge without tightly coupling to backend vector indexes, SQL databases, Git trees, or filesystem hierarchies.

## Request Lifecycle
1. **Client Dispatches Query**: Payload includes natural language prompt, tags, target sources, and pagination parameters.
2. **Parallel Fan-out**: The gateway queries RAG, OKF, Filesystem, Git, and SQL in parallel with per-source latency bounds.
3. **ONNX Reranker & Consolidation**: Raw candidate items are transformed into feature vectors and scored by the local ONNX neural network.
4. **Pagination**: Results are sliced deterministically based on `page` and `page_size`, returning `has_next` and page tokens.
5. **Activity Log & Tailing**: Audit metadata is logged to the in-memory circular buffer and broadcasted to live tailing subscribers.

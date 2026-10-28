import pytest
from src.gateway import KnowledgeGateway
from src.models import GatewayQuery
from src.config import load_config


@pytest.mark.asyncio
async def test_end_to_end_gateway_retrieval():
    config = load_config()
    gateway = KnowledgeGateway(config)

    # Multi-source prompt testing WeftKit, Vault, PCI compliance, Tauri
    query_req = GatewayQuery(
        query="WeftKit architecture, vault secrets, and PCI DSS compliance standard",
        tags=["vault", "pci-dss", "architecture"],
        page=1,
        page_size=10,
        min_score=0.10,
    )

    response = await gateway.query(query_req)

    # 1. Assert response structure
    assert response.query == query_req.query
    assert response.total_results > 0
    assert len(response.items) > 0
    assert response.latency_ms > 0

    # 2. Check that items come from multiple heterogeneous sources
    sources_represented = {item.source_type for item in response.items}
    # Should represent at least OKF, Filesystem, and/or RAG
    assert len(sources_represented) >= 2, f"Expected multi-source representation, got: {sources_represented}"

    # 3. Verify ONNX scores are ordered descending
    scores = [item.score for item in response.items]
    assert scores == sorted(scores, reverse=True), "Items not sorted descending by ONNX score"

    # 4. Verify provenance details exist
    for it in response.items:
        assert it.id
        assert it.source_type
        assert it.title
        assert it.content
        assert it.score >= query_req.min_score
        assert isinstance(it.provenance, dict)
        assert len(it.provenance) > 0

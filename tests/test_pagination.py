import pytest
from src.gateway import KnowledgeGateway
from src.models import GatewayQuery
from src.config import GatewayConfig, load_config


@pytest.mark.asyncio
async def test_deterministic_pagination():
    config = load_config()
    gateway = KnowledgeGateway(config)

    # Issue query with page_size=2, page=1
    q1 = GatewayQuery(
        query="Enterprise architecture security vault payment",
        page=1,
        page_size=2,
        min_score=0.05,
    )
    res_page1 = await gateway.query(q1)

    assert res_page1.page == 1
    assert res_page1.page_size == 2
    assert len(res_page1.items) <= 2
    assert res_page1.has_previous is False

    if res_page1.total_results > 2:
        assert res_page1.has_next is True

        # Query page 2
        q2 = GatewayQuery(
            query="Enterprise architecture security vault payment",
            page=2,
            page_size=2,
            min_score=0.05,
        )
        res_page2 = await gateway.query(q2)

        assert res_page2.page == 2
        assert res_page2.has_previous is True

        page1_ids = {it.id for it in res_page1.items}
        page2_ids = {it.id for it in res_page2.items}
        # Non-overlapping slices
        assert len(page1_ids & page2_ids) == 0

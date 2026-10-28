import pytest
from pathlib import Path
from src.onnx_engine import ONNXConsolidatorEngine
from src.config import ONNXEngineConfig
from src.models import GatewayKnowledgeItem


def test_onnx_engine_initialization():
    config = ONNXEngineConfig(
        enabled=True,
        model_path="models/reranker.onnx",
        score_threshold=0.15,
    )
    engine = ONNXConsolidatorEngine(config)
    assert engine.is_onnx_active is True
    assert engine.session is not None


def test_onnx_engine_scoring_and_ranking():
    config = ONNXEngineConfig(
        enabled=True,
        model_path="models/reranker.onnx",
        score_threshold=0.10,
    )
    engine = ONNXConsolidatorEngine(config)

    item_high = GatewayKnowledgeItem(
        id="item_high",
        source_type="okf",
        title="HashiCorp Vault Secrets Engine",
        content="HashiCorp Vault manages secrets, transit encryption, and database credentials.",
        snippet="Vault transit encryption",
        raw_score=0.90,
        metadata={"tags": ["vault", "secrets", "security"]},
    )

    item_low = GatewayKnowledgeItem(
        id="item_low",
        source_type="filesystem",
        title="Unrelated Recipe Notes",
        content="Making homemade pizza dough with flour and water.",
        snippet="Pizza recipe",
        raw_score=0.10,
        metadata={"tags": ["cooking"]},
    )

    scored_items, traces = engine.consolidate_and_rerank(
        query="Which services handle vault secrets and encryption?",
        tags=["vault", "secrets"],
        candidates=[item_low, item_high],
    )

    assert len(scored_items) >= 1
    assert scored_items[0].id == "item_high"
    assert scored_items[0].score > 0.5
    assert len(traces) == 2


def test_onnx_deduplication():
    engine = ONNXConsolidatorEngine(ONNXEngineConfig(enabled=True, model_path="models/reranker.onnx"))

    item1 = GatewayKnowledgeItem(
        id="dup_item",
        source_type="okf",
        title="Duplicate Entity",
        content="Same content body here.",
        snippet="Same content",
        raw_score=0.8,
    )
    item2 = GatewayKnowledgeItem(
        id="dup_item",
        source_type="okf",
        title="Duplicate Entity",
        content="Same content body here.",
        snippet="Same content",
        raw_score=0.8,
    )

    scored_items, _ = engine.consolidate_and_rerank(
        query="Duplicate Entity",
        tags=[],
        candidates=[item1, item2],
    )

    assert len(scored_items) == 1

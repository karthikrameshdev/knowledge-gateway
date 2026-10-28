import pytest
from starlette.testclient import TestClient
from src.server import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "onnx_model_active" in data


def test_config_endpoint(client):
    res = client.get("/api/v1/config")
    assert res.status_code == 200
    data = res.json()
    assert "gateway" in data
    assert "rag" in data


def test_sources_status_endpoint(client):
    res = client.get("/api/v1/sources/status")
    assert res.status_code == 200
    data = res.json()
    assert "rag" in data
    assert "okf" in data
    assert "filesystem" in data
    assert "git" in data
    assert "onnx_engine" in data


def test_query_and_activity_audit(client):
    payload = {
        "query": "Which services depend on vault secrets engine?",
        "tags": ["vault", "security"],
        "page": 1,
        "page_size": 3,
        "min_score": 0.05,
    }
    res = client.post("/api/v1/query", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["page"] == 1
    assert data["page_size"] == 3
    assert "items" in data
    assert "sources_searched" in data
    assert len(data["items"]) >= 1

    # Verify Activity Log
    act_res = client.get("/api/v1/activity?limit=10")
    assert act_res.status_code == 200
    act_data = act_res.json()
    assert act_data["total"] >= 1
    first_entry = act_data["entries"][0]
    req_id = first_entry["request_id"]

    # Verify Activity Detail Inspection
    detail_res = client.get(f"/api/v1/activity/{req_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["request_id"] == req_id
    assert "source_breakdown" in detail
    assert "candidates_reranking" in detail
    assert "response_payload" in detail


def test_ui_index_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Knowledge Gateway" in res.text
    assert "Live Tailing" in res.text

import pytest
from pathlib import Path
from src.config import EmbeddingConfig, OKFConfig, FilesystemConfig, FilesystemDirectoryConfig, GitConfig, GitRepoConfig, RAGConfig
from src.connectors.okf_connector import OKFConnector
from src.connectors.fs_connector import FilesystemConnector
from src.connectors.git_connector import GitConnector
from src.connectors.rag_connector import RAGConnector


@pytest.mark.asyncio
async def test_okf_connector():
    config = OKFConfig(enabled=True, root_dir="data/okf", deterministic_traversal=True)
    connector = OKFConnector(config)
    health = await connector.health_check()
    assert health["status"] == "healthy"
    assert health["documents_count"] >= 3

    # Test relational query for vault
    results = await connector.search("Which services depend on vault secrets?", tags=["vault"])
    assert len(results) >= 1
    ids = [r.id for r in results]
    assert "vault-secrets-engine" in ids or any("payment-gateway" in i for i in ids)


@pytest.mark.asyncio
async def test_filesystem_connector():
    config = FilesystemConfig(
        enabled=True,
        directories=[
            FilesystemDirectoryConfig(path="data/docs", patterns=["*.md"]),
            FilesystemDirectoryConfig(path="data/specs", patterns=["*.md"]),
        ],
        max_results=5,
    )
    connector = FilesystemConnector(config)
    health = await connector.health_check()
    assert health["status"] == "healthy"
    assert health["total_files"] >= 2

    results = await connector.search("Enterprise desktop architecture guide", tags=[])
    assert len(results) >= 1
    assert any("architecture" in r.title.lower() or "enterprise" in r.title.lower() for r in results)


@pytest.mark.asyncio
async def test_git_connector():
    config = GitConfig(
        enabled=True,
        repositories=[
            GitRepoConfig(name="test-repo", path=".", branch="main", max_commits=10)
        ],
    )
    connector = GitConnector(config)
    health = await connector.health_check()
    assert health["status"] in ["healthy", "degraded"]

    results = await connector.search("Initial commit", tags=[])
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_rag_connector():
    config = RAGConfig(
        enabled=True,
        provider="qdrant",
        mode="memory",
        embedding=EmbeddingConfig(provider="deterministic"),
        host="localhost",
        port=6333,
        collection="test_unit_rag_col",
    )
    connector = RAGConnector(config)
    health = await connector.health_check()
    assert health["status"] in ["healthy", "degraded"]

    # Index sample documents
    connector.index_seed_documents([
        {
            "id": "rag_test_1",
            "title": "Tauri Architecture Bridge",
            "content": "Tauri IPC is used for desktop system operations.",
            "category": "architecture",
            "tags": ["tauri", "desktop"],
        }
    ])

    results = await connector.search("Tauri desktop IPC bridge", tags=["tauri"])
    assert len(results) >= 1
    assert results[0].source_type == "rag"

import pytest
from src.config import SQLConfig, SQLTableConfig
from src.connectors.sql_connector import SQLConnector


@pytest.mark.asyncio
async def test_live_docker_postgres_connector():
    config = SQLConfig(
        enabled=True,
        provider="postgresql",
        host="localhost",
        port=5433,
        database="weftkit_db",
        username="weftkit_admin",
        password="weftkit_secret",
        timeout_seconds=3.0,
        tables=[
            SQLTableConfig(
                table_name="weftkit_knowledge",
                search_columns=["title", "content", "category", "tags"],
                id_column="id",
                title_column="title",
                content_column="content",
            ),
            SQLTableConfig(
                table_name="weftkit_configs",
                search_columns=["config_key", "config_value", "description", "scope"],
                id_column="id",
                title_column="config_key",
                content_column="description",
            ),
        ],
    )
    connector = SQLConnector(config)
    health = await connector.health_check()
    if health.get("status") == "unreachable":
        pytest.skip("Docker PostgreSQL container is not currently running on port 5433")

    assert health["status"] == "healthy"
    assert "weftkit_knowledge" in health["tables"]

    # Search for OAuth
    results = await connector.search("Google OAuth Tauri desktop flow", tags=["oauth"])
    assert len(results) >= 1
    assert any("oauth" in r.title.lower() or "google" in r.title.lower() for r in results)

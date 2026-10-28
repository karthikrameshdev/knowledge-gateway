import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal
import yaml
from pydantic import BaseModel, Field, model_validator, ConfigDict


def _expand_env_vars(text: str) -> str:
    """Expands ${VAR} or ${VAR:-default} from environment variables."""
    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")

    def replacer(match):
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return pattern.sub(replacer, text)


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True, allow_inf_nan=False)


class PaginationConfig(ConfigModel):
    default_page_size: int = Field(default=5, ge=1, le=50)
    max_page_size: int = Field(default=50, ge=1, le=50)

    @model_validator(mode="after")
    def valid_range(self):
        if self.default_page_size > self.max_page_size:
            raise ValueError("default_page_size exceeds max_page_size")
        return self


class ONNXEngineConfig(ConfigModel):
    enabled: bool = True
    model_path: str = "models/reranker.onnx"
    score_threshold: float = 0.15



class GatewayServerConfig(ConfigModel):
    name: str = "Knowledge Gateway"
    version: str = "1.1.0"
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    debug: bool = False
    demo_mode: bool = False
    source_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    max_concurrent_queries: int = Field(default=16, ge=1, le=128)
    queue_timeout_seconds: float = Field(default=0.25, gt=0, le=10)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    onnx_engine: ONNXEngineConfig = Field(default_factory=ONNXEngineConfig)


class EmbeddingConfig(ConfigModel):
    provider: Literal["openai", "deterministic"] = "openai"
    openai_url: str = "https://openrouter.ai/api/v1"
    model_id: str = "openai/text-embedding-3-small"
    api_key: str = ""
    dimension: int = Field(default=768, ge=1, le=8192)
    timeout_seconds: float = Field(default=4.0, gt=0, le=30)
    send_dimensions: bool = True


class RAGConfig(ConfigModel):
    mode: Literal["remote", "memory"] = "remote"
    timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    enabled: bool = True
    provider: Literal["qdrant"] = "qdrant"
    host: str = "localhost"
    port: int = 6333
    collection: str = "enterprise_knowledge_rag"
    top_k: int = Field(default=8, ge=1, le=100)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


class OKFConfig(ConfigModel):
    enabled: bool = True
    root_dir: str = "data/okf"
    deterministic_traversal: bool = True
    top_k: int = Field(default=8, ge=1, le=100)
    refresh_interval_seconds: float = Field(default=2.0, ge=0)
    max_files: int = Field(default=2000, ge=1, le=100000)
    max_file_bytes: int = Field(default=262144, ge=1, le=10485760)


class FilesystemDirectoryConfig(ConfigModel):
    path: str
    patterns: List[str] = Field(default_factory=lambda: ["*.md", "*.txt"])


class FilesystemConfig(ConfigModel):
    enabled: bool = True
    directories: List[FilesystemDirectoryConfig] = Field(default_factory=list)
    max_results: int = Field(default=8, ge=1, le=100)
    max_files: int = Field(default=2000, ge=1, le=100000)
    max_file_bytes: int = Field(default=262144, ge=1, le=10485760)


class GitRepoConfig(ConfigModel):
    name: str = "repo"
    path: str = "."
    branch: str = "main"
    max_commits: int = Field(default=15, ge=1, le=1000)
    max_results: int = Field(default=6, ge=1, le=100)

    @model_validator(mode="after")
    def safe_ref(self):
        if not self.branch or self.branch.startswith('-') or len(self.branch) > 256:
            raise ValueError("branch must be a Git revision, not a command option")
        return self


class GitConfig(ConfigModel):
    enabled: bool = True
    repositories: List[GitRepoConfig] = Field(default_factory=list)


class SQLTableConfig(ConfigModel):
    table_name: str
    search_columns: List[str]
    id_column: str = "id"
    title_column: str = "title"
    content_column: str = "content"


class SQLConfig(ConfigModel):
    enabled: bool = True
    provider: Literal["postgresql"] = "postgresql"
    host: str = "localhost"
    port: int = 5433
    database: str = "gateway_db"
    username: "str" = "postgres_admin"
    password: str = "postgres_secret"
    timeout_seconds: float = Field(default=4.0, ge=1, le=30)
    tables: List[SQLTableConfig] = Field(default_factory=list)
    max_results: int = Field(default=8, ge=1, le=100)


class RedisConfig(ConfigModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    timeout_seconds: float = Field(default=0.5, gt=0, le=10)
    retry_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    key_prefix: str = "kg:cache:"


class CacheConfig(ConfigModel):
    namespace: str = Field(default="knowledge-gateway-v1.1", min_length=1, max_length=128)
    enabled: bool = True
    backend: Literal["redis", "memory"] = "memory"
    ttl_seconds: int = Field(default=300, ge=1, le=86400)
    eviction_policy: Literal["lru", "lfu", "fifo"] = "lru"
    max_entries: int = Field(default=1000, ge=1, le=100000)
    max_value_bytes: int = Field(default=2097152, ge=1024, le=16777216)
    redis: RedisConfig = Field(default_factory=RedisConfig)


class SecurityConfig(ConfigModel):
    api_key: str = ""
    cors_origins: List[str] = Field(default_factory=list)
    allowed_hosts: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "[::1]", "testserver"])


class GatewayConfig(ConfigModel):
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    gateway: GatewayServerConfig = Field(default_factory=GatewayServerConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    okf: OKFConfig = Field(default_factory=OKFConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    sql: SQLConfig = Field(default_factory=SQLConfig)


def load_config(config_path: Optional[str] = None) -> GatewayConfig:
    """Loads and parses the gateway YAML configuration file."""
    # Try multiple standard paths if none provided
    config_path = config_path or os.environ.get("KNOWLEDGE_GATEWAY_CONFIG")
    candidates = []
    if config_path:
        explicit = Path(config_path)
        if not explicit.is_file():
            raise FileNotFoundError("Explicit gateway configuration does not exist")
        candidates.append(explicit)
    candidates.extend([
        Path("config.yaml"),
        Path("config.yml"),
        Path(__file__).resolve().parent.parent / "config.yaml",
    ])

    chosen_path = None
    for p in candidates:
        if p.exists() and p.is_file():
            chosen_path = p
            break

    if not chosen_path:
        # Return sensible default configuration
        return GatewayConfig()

    content = chosen_path.read_text(encoding="utf-8")
    # Expand values after parsing: quotes/newlines in secrets must remain data, not YAML.
    def expand(value):
        if isinstance(value, str):
            return _expand_env_vars(value)
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value
    raw_data = expand(yaml.safe_load(content) or {})
    if not isinstance(raw_data, dict):
        raise ValueError("Gateway configuration must be a YAML mapping")
    raw_data.setdefault("security", {})
    if "KNOWLEDGE_GATEWAY_API_KEY" in os.environ:
        raw_data["security"]["api_key"] = os.environ["KNOWLEDGE_GATEWAY_API_KEY"]
    return GatewayConfig(**raw_data)

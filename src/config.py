import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from pydantic import BaseModel, Field


def _expand_env_vars(text: str) -> str:
    """Expands ${VAR} or ${VAR:-default} from environment variables."""
    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")

    def replacer(match):
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return pattern.sub(replacer, text)


class PaginationConfig(BaseModel):
    default_page_size: int = 5
    max_page_size: int = 50


class ONNXEngineConfig(BaseModel):
    enabled: bool = True
    model_path: str = "models/reranker.onnx"
    score_threshold: float = 0.15
    weights: Dict[str, float] = Field(default_factory=lambda: {
        "semantic_sim": 0.35,
        "lexical_overlap": 0.20,
        "title_match": 0.20,
        "tag_match": 0.10,
        "source_confidence": 0.15,
    })


class GatewayServerConfig(BaseModel):
    name: str = "Knowledge Gateway"
    version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = True
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    onnx_engine: ONNXEngineConfig = Field(default_factory=ONNXEngineConfig)


class EmbeddingConfig(BaseModel):
    openai_url: str = "https://openrouter.ai/api/v1"
    model_id: str = "openai/text-embedding-3-small"
    api_key: str = ""
    dimension: int = 768


class RAGConfig(BaseModel):
    enabled: bool = True
    provider: str = "qdrant"
    host: str = "localhost"
    port: int = 6333
    collection: str = "weftkit_knowledge_rag"
    top_k: int = 8
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


class OKFConfig(BaseModel):
    enabled: bool = True
    root_dir: str = "data/okf"
    deterministic_traversal: bool = True
    top_k: int = 8


class FilesystemDirectoryConfig(BaseModel):
    path: str
    patterns: List[str] = Field(default_factory=lambda: ["*.md", "*.txt"])


class FilesystemConfig(BaseModel):
    enabled: bool = True
    directories: List[FilesystemDirectoryConfig] = Field(default_factory=list)
    max_results: int = 8


class GitRepoConfig(BaseModel):
    name: str = "repo"
    path: str = "."
    branch: str = "main"
    max_commits: int = 15
    max_results: int = 6


class GitConfig(BaseModel):
    enabled: bool = True
    repositories: List[GitRepoConfig] = Field(default_factory=list)


class SQLTableConfig(BaseModel):
    table_name: str
    search_columns: List[str]
    id_column: str = "id"
    title_column: str = "title"
    content_column: str = "content"


class SQLConfig(BaseModel):
    enabled: bool = True
    provider: str = "postgresql"
    host: str = "localhost"
    port: int = 5433
    database: str = "weftkit_db"
    username: str = "weftkit_admin"
    password: str = "weftkit_secret"
    timeout_seconds: float = 4.0
    tables: List[SQLTableConfig] = Field(default_factory=list)
    max_results: int = 8


class GatewayConfig(BaseModel):
    gateway: GatewayServerConfig = Field(default_factory=GatewayServerConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    okf: OKFConfig = Field(default_factory=OKFConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    sql: SQLConfig = Field(default_factory=SQLConfig)


def load_config(config_path: Optional[str] = None) -> GatewayConfig:
    """Loads and parses the gateway YAML configuration file."""
    # Try multiple standard paths if none provided
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
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
    expanded_content = _expand_env_vars(content)
    raw_data = yaml.safe_load(expanded_content) or {}
    return GatewayConfig(**raw_data)

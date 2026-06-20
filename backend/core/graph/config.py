"""
图数据库配置管理
"""

import os
import re
import logging
from dataclasses import dataclass, field, replace
from typing import Optional, Dict, Any


@dataclass
class WeaviateConfig:
    url: str = "http://localhost:8080"
    api_key: Optional[str] = None
    vector_dim: int = 768
    batch_size: int = 100
    ef_construction: int = 128
    max_connections: int = 16


@dataclass
class EmbeddingConfig:
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 32
    device: str = "cpu"
    cache_folder: Optional[str] = None


@dataclass
class GraphConfig:
    database_path: str = "data/graph.db"
    auto_create_schema: bool = True
    pool_size: int = 10
    timeout: int = 30
    weaviate: WeaviateConfig = field(default_factory=WeaviateConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


_config: Optional[GraphConfig] = None

logger = logging.getLogger(__name__)


def get_graph_config(agent_id: Optional[str] = None) -> GraphConfig:
    """获取图数据库配置。

    当 ``agent_id`` 为 None 或 ``'default'`` 时返回全局单例配置；
    否则基于默认配置生成按助手的配置，db_path 形如
    ``data/graph_{agent_id}.db``。
    """
    global _config
    # 默认情况：使用单例
    if agent_id is None or agent_id == 'default':
        if _config is not None:
            return _config
        try:
            from config.settings import settings
            unified = settings.config
            if hasattr(unified, 'graph') and unified.graph.enabled:
                gc = unified.graph
                _config = GraphConfig(
                    database_path=gc.database_path,
                    auto_create_schema=gc.auto_create_schema,
                    pool_size=gc.pool_size,
                    timeout=gc.timeout,
                    weaviate=WeaviateConfig(
                        url=gc.weaviate.url,
                        api_key=gc.weaviate.api_key,
                        vector_dim=gc.weaviate.vector_dim,
                        batch_size=gc.weaviate.batch_size,
                        ef_construction=gc.weaviate.ef_construction,
                        max_connections=gc.weaviate.max_connections,
                    ),
                    embedding=EmbeddingConfig(
                        model=gc.embedding.model,
                        batch_size=gc.embedding.batch_size,
                        device=gc.embedding.device,
                        cache_folder=gc.embedding.cache_folder,
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to load graph config from settings: {e}")
        if _config is None:
            _config = _load_config_from_env()
        return _config

    # 按助手情况：基于默认配置生成 per-agent db_path
    base = get_graph_config()
    safe_id = re.sub(r'[\\/:*?"<>|]', '_', agent_id)
    per_agent_path = f"data/graph_{safe_id}.db"
    return replace(base, database_path=per_agent_path)


def _load_config_from_env() -> GraphConfig:
    return GraphConfig(
        database_path=os.getenv("GRAPH_DATABASE_PATH", "data/graph.db"),
        auto_create_schema=os.getenv("GRAPH_AUTO_CREATE", "true").lower() == "true",
        pool_size=int(os.getenv("GRAPH_POOL_SIZE", "10")),
        timeout=int(os.getenv("GRAPH_TIMEOUT", "30")),
        weaviate=WeaviateConfig(
            url=os.getenv("WEAVIATE_URL", "http://localhost:8080"),
            api_key=os.getenv("WEAVIATE_API_KEY"),
            vector_dim=int(os.getenv("WEAVIATE_VECTOR_DIM", "768")),
            batch_size=int(os.getenv("WEAVIATE_BATCH_SIZE", "100")),
            ef_construction=int(os.getenv("WEAVIATE_EF_CONSTRUCTION", "128")),
            max_connections=int(os.getenv("WEAVIATE_MAX_CONNECTIONS", "16")),
        ),
        embedding=EmbeddingConfig(
            model=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
            device=os.getenv("EMBEDDING_DEVICE", "cpu"),
            cache_folder=os.getenv("EMBEDDING_CACHE_FOLDER"),
        ),
    )


def set_graph_config(config: GraphConfig) -> None:
    global _config
    _config = config

"""
语义检索
"""

import logging
from typing import Optional, List, Dict, Any, Callable
import numpy as np

from backend.core.graph.config import GraphConfig, get_graph_config
from backend.core.graph.vectorizer import get_vectorizer, TextVectorizer
from backend.core.graph.models import GraphNode, SemanticSearchResult

logger = logging.getLogger(__name__)


class SemanticSearch:
    """语义搜索"""

    def __init__(self, config: GraphConfig = None):
        self.config = config or get_graph_config()
        self._client = None
        self._vectorizer = get_vectorizer()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        try:
            import weaviate
            self._client = weaviate.Client(
                url=self.config.weaviate.url,
                auth_client_secret=weaviate.AuthApiKey(self.config.weaviate.api_key)
                    if self.config.weaviate.api_key else None,
            )
            self._ensure_schema()
            self._initialized = True
            logger.info(f"语义搜索初始化完成: {self.config.weaviate.url}")
        except ImportError:
            logger.warning("weaviate-client 未安装，语义搜索将使用本地模式")
            self._client = None
        except Exception as e:
            logger.warning(f"连接 Weaviate 失败: {e}，使用本地模式")
            self._client = None

    def _ensure_schema(self) -> None:
        if not self._client:
            return

        schema = {
            "class": "GraphNode",
            "description": "图数据库节点向量索引",
            "vectorizer": "none",
            "vectorIndexConfig": {
                "efConstruction": self.config.weaviate.ef_construction,
                "maxConnections": self.config.weaviate.max_connections,
            },
            "properties": [
                {"name": "node_id", "dataType": ["string"]},
                {"name": "node_type", "dataType": ["string"]},
                {"name": "text_content", "dataType": ["text"]},
                {"name": "agent_id", "dataType": ["string"]},
            ]
        }

        try:
            if not self._client.schema.exists("GraphNode"):
                self._client.schema.create_class(schema)
                logger.info("创建 Weaviate schema: GraphNode")
        except Exception as e:
            logger.warning(f"创建 schema 失败: {e}")

    def add_vector(
        self,
        node_id: str,
        text_content: str,
        node_type: str,
        vector: Optional[np.ndarray] = None,
        agent_id: str = "default",
    ) -> str:
        if vector is None:
            vector = self._vectorizer.encode(text_content)

        if self._client:
            try:
                vector_id = f"{node_id}_vector"
                self._client.data_object.create(
                    class_name="GraphNode",
                    data_object={
                        "node_id": node_id,
                        "node_type": node_type,
                        "text_content": text_content,
                        "agent_id": agent_id,
                    },
                    vector=vector.tolist(),
                )
                return vector_id
            except Exception as e:
                logger.error(f"添加向量失败: {e}")
                return node_id
        else:
            return node_id

    def search(
        self,
        query: str,
        node_type: Optional[str] = None,
        limit: int = 10,
        node_filter: Optional[Callable[[str], bool]] = None,
        agent_id: str = "default",
    ) -> List[SemanticSearchResult]:
        if not self._initialized:
            self.initialize()

        results = []

        if self._client:
            try:
                query_vector = self._vectorizer.encode(query)

                where_filter = None
                if node_type and agent_id and agent_id != "default":
                    where_filter = {
                        "operator": "And",
                        "operands": [
                            {
                                "path": ["node_type"],
                                "operator": "Equal",
                                "valueString": node_type,
                            },
                            {
                                "path": ["agent_id"],
                                "operator": "Equal",
                                "valueString": agent_id,
                            },
                        ]
                    }
                elif node_type:
                    where_filter = {
                        "path": ["node_type"],
                        "operator": "Equal",
                        "valueString": node_type
                    }
                elif agent_id and agent_id != "default":
                    where_filter = {
                        "path": ["agent_id"],
                        "operator": "Equal",
                        "valueString": agent_id
                    }

                search = self._client.query.get(
                    "GraphNode",
                    ["node_id", "node_type", "text_content", "agent_id", "_additional {certainty}"]
                ).with_near_vector(
                    {"vector": query_vector.tolist()}
                ).with_limit(limit)

                if where_filter:
                    search = search.with_where(where_filter)

                response = search.do()
                nodes = response.get("data", {}).get("Get", {}).get("GraphNode", [])

                for item in nodes:
                    score = item.get("_additional", {}).get("certainty", 0.0)
                    node = GraphNode(
                        id=item["node_id"],
                        type=item.get("node_type", ""),
                        text_content=item.get("text_content"),
                    )
                    results.append(SemanticSearchResult(
                        node=node,
                        score=score,
                    ))

            except Exception as e:
                logger.error(f"语义搜索失败: {e}")
                results = []

        if not results:
            results = self._fallback_search(query, node_type, limit, node_filter, agent_id)

        return results

    def _fallback_search(
        self,
        query: str,
        node_type: Optional[str],
        limit: int,
        node_filter: Optional[Callable],
        agent_id: str = "default",
    ) -> List[SemanticSearchResult]:
        query_words = set(query.lower().split())
        results = []

        from backend.core.graph.database import get_database
        db = get_database(self.config)

        sql = "SELECT * FROM nodes WHERE text_content IS NOT NULL"
        params = []
        if node_type:
            sql += " AND type = ?"
            params.append(node_type)
        if agent_id and agent_id != "default":
            sql += " AND agent_id = ?"
            params.append(agent_id)

        rows = db.execute(sql, tuple(params))

        for row in rows:
            node = GraphNode.from_dict(dict(row))
            if node_filter and not node_filter(node.id):
                continue

            text_words = set(node.text_content.lower().split())
            score = len(query_words & text_words) / max(len(query_words), 1)

            if score > 0:
                results.append(SemanticSearchResult(
                    node=node,
                    score=score,
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def delete_vector(self, node_id: str) -> bool:
        if self._client:
            try:
                self._client.data_object.delete(
                    class_name="GraphNode",
                    where={"path": ["node_id"], "operator": "Equal", "valueString": node_id}
                )
                return True
            except Exception as e:
                logger.error(f"删除向量失败: {e}")
        return False

    def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.schema.get()
            return True
        except Exception as e:
            logger.error(f"Weaviate 健康检查失败: {e}")
            return False

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        return self._vectorizer.encode_batch(texts)

    def compute_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        if len(vec1) != len(vec2):
            return 0.0
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))

    def close(self) -> None:
        if self._client:
            self._client = None
        self._initialized = False

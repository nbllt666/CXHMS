"""
语义图数据库 - SQLite + Weaviate
轻量级图数据库，支持语义检索
"""

from backend.core.graph.database import Database, get_database, get_database_if_exists, remove_database
from backend.core.graph.models import GraphNode, GraphEdge, NodeCreate, EdgeCreate
from backend.core.graph.nodes import NodeManager
from backend.core.graph.edges import EdgeManager
from backend.core.graph.repository import BaseGraphRepository
from backend.core.graph.traversal import TraversalManager
from backend.core.graph.vectorizer import TextVectorizer, get_vectorizer
from backend.core.graph.semantic_search import SemanticSearch
from backend.core.graph.hybrid_query import HybridQueryManager
from backend.core.graph.visualization import GraphExporter
from backend.core.graph.semantic_query import SemanticQueryManager
from backend.core.graph.monitoring import GraphMonitor
from backend.core.graph.config import GraphConfig, get_graph_config

__all__ = [
    "Database",
    "get_database",
    "get_database_if_exists",
    "remove_database",
    "GraphNode",
    "GraphEdge",
    "NodeCreate",
    "EdgeCreate",
    "NodeManager",
    "EdgeManager",
    "BaseGraphRepository",
    "TraversalManager",
    "SemanticSearch",
    "HybridQueryManager",
    "SemanticQueryManager",
    "GraphExporter",
    "GraphMonitor",
    "TextVectorizer",
    "get_vectorizer",
    "GraphConfig",
    "get_graph_config",
]


class GraphDatabase:
    """语义图数据库主入口"""

    def __init__(self, config: GraphConfig = None, agent_id: str = "default"):
        self.agent_id = agent_id
        self.config = config or get_graph_config(agent_id=agent_id)
        self.db = get_database(self.config, agent_id=agent_id)
        self.nodes = NodeManager(self.db, self.config)
        self.edges = EdgeManager(self.db, self.config)
        self.traversal = TraversalManager(self.db, self.config)
        self.semantic = SemanticSearch(self.config)
        self.hybrid = HybridQueryManager(self.db, self.semantic, self.config)

    def initialize(self) -> None:
        self.db.initialize()
        self.semantic.initialize()

    def close(self) -> None:
        self.db.close()
        self.semantic.close()

    def health_check(self) -> dict:
        db_healthy = self.db.health_check()
        semantic_healthy = self.semantic.health_check()
        return {
            "database": "healthy" if db_healthy else "unhealthy",
            "semantic": "healthy" if semantic_healthy else "unhealthy",
            "overall": "healthy" if db_healthy and semantic_healthy else "degraded",
        }

"""GraphService 接口契约存根。

对应 backend/api/routers/graph.py 的路由与 backend/core/graph/ 下的 NodeManager/EdgeManager/TraversalManager/SemanticSearch。
零实现逻辑，仅声明签名。模块实现必须严格匹配本存根。

@version 1.0.0
@see public/schema/memory.json (GraphNode/GraphEdge 在 backend/core/graph/models.py)
"""

from typing import Any, Dict, List, Optional


class GraphService:
    """图数据库服务接口。

    提供节点/边的 CRUD、遍历、语义搜索与最短路径查询能力。
    按 agent_id 隔离图空间。未启用图数据库时返回 404。
    """

    async def create_node(self, request: Dict[str, Any], agent_id: str = "default") -> Dict[str, Any]:
        """创建图节点，返回 GraphNode dict。

        Raises:
            DatabaseError: 持久化失败
            ValidationError: type 为空
        """
        ...

    async def get_node(self, node_id: str, agent_id: str = "default") -> Optional[Dict[str, Any]]:
        """获取节点；不存在返回 None。

        Raises:
            DatabaseError: 查询失败
        """
        ...

    async def update_node(
        self, node_id: str, request: Dict[str, Any], agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """更新节点；返回更新后节点，不存在返回 None。

        Raises:
            DatabaseError: 更新失败
        """
        ...

    async def delete_node(
        self, node_id: str, cascade: bool = True, agent_id: str = "default"
    ) -> bool:
        """删除节点。cascade=True 时连带删除关联边。返回是否成功。

        Raises:
            DatabaseError: 删除失败
        """
        ...

    async def create_edge(self, request: Dict[str, Any], agent_id: str = "default") -> Dict[str, Any]:
        """创建图边（关系），返回 GraphEdge dict。

        Raises:
            DatabaseError: 持久化失败
            ValidationError: source_id/target_id 不存在
        """
        ...

    async def get_edge(self, edge_id: str, agent_id: str = "default") -> Optional[Dict[str, Any]]:
        """获取边；不存在返回 None。"""
        ...

    async def update_edge(
        self, edge_id: str, request: Dict[str, Any], agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """更新边。"""
        ...

    async def delete_edge(self, edge_id: str, agent_id: str = "default") -> bool:
        """删除边。"""
        ...

    async def traverse_bfs(
        self,
        start_id: str,
        max_depth: int = 10,
        node_type_filter: Optional[str] = None,
        agent_id: str = "default",
    ) -> Dict[str, Any]:
        """广度优先遍历，返回 {nodes, edges, visited_count}。

        Raises:
            DatabaseError: 起点不存在或查询失败
        """
        ...

    async def traverse_dfs(
        self,
        start_id: str,
        max_depth: int = 10,
        node_type_filter: Optional[str] = None,
        agent_id: str = "default",
    ) -> Dict[str, Any]:
        """深度优先遍历。"""
        ...

    async def shortest_path(
        self, start_id: str, end_id: str, max_length: int = 10, agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """最短路径查询，返回 {path, edges, length}；不可达返回 None。按 agent_id 隔离图空间。

        Raises:
            DatabaseError: 端点不存在或查询失败
        """
        ...

    async def semantic_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        limit: int = 10,
        agent_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """图节点语义搜索，返回 [{node, score}]。

        Raises:
            VectorStoreError: 向量库未启用或查询失败
        """
        ...

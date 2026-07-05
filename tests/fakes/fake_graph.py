"""内存图存储的假实现，用于端到端测试。

不依赖 SQLite / Weaviate，所有节点保存在 dict、边保存在 dict（按 id 索引）。
覆盖 ``SQLiteGraphStore`` / ``GraphDatabase`` 在聊天、记忆写入检索、工具调用场景中
实际被触发的方法；未覆盖的方法返回合理默认值（空 list / None / False）。

设计原则：
- ``InMemoryGraphDatabase`` 提供底层邻接存储与图遍历原语。
- ``InMemoryGraphStore`` 实现 ``GraphStoreBase`` 契约，把 Entity/Relation 映射到
  GraphNode/GraphEdge 并委托给底层图数据库（与真实 ``SQLiteGraphStore`` 结构一致）。
- ``make_in_memory_graph_store`` 工厂返回 (graph_database, graph_store) 元组。
"""

import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.core.graph.models import GraphEdge, GraphNode, PathResult, SearchResult
from backend.core.memory.graph_store import (
    Entity,
    GraphLibrary,
    GraphStoreBase,
    Relation,
)


class InMemoryGraphDatabase:
    """轻量内存图数据库。

    用 dict 存节点、dict 存边（按 id 索引），仅覆盖测试中实际被调用的核心方法：
    生命周期（initialize/close/health_check）、节点/边 CRUD、搜索、邻居与路径遍历。
    未覆盖的方法返回合理默认值。
    """

    def __init__(self, agent_id: str = "default", config: Any = None):
        self.agent_id = agent_id
        self.config = config
        # `graph.db` 在部分代码路径中被访问，指向自身以保持兼容
        self.db = self
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[str, GraphEdge] = {}
        self._lock = threading.Lock()
        self._closed = False

    # ---------------- 生命周期 ----------------
    def initialize(self) -> None:
        self._closed = False

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._nodes.clear()
            self._edges.clear()

    def health_check(self) -> Dict[str, str]:
        return {"database": "healthy", "semantic": "healthy", "overall": "healthy"}

    # ---------------- 节点 ----------------
    def add_node(
        self,
        node_type: str,
        properties: Optional[Dict[str, Any]] = None,
        text_content: Optional[str] = None,
        agent_id: str = "default",
    ) -> GraphNode:
        node = GraphNode.create(
            type=node_type,
            properties=dict(properties or {}),
            text_content=text_content,
            agent_id=agent_id,
        )
        with self._lock:
            self._nodes[node.id] = node
        return node

    def get_node(self, node_id: str, agent_id: str = "default") -> Optional[GraphNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def update_node(
        self,
        node_id: str,
        properties: Optional[Dict[str, Any]] = None,
        type: Optional[str] = None,
        text_content: Optional[str] = None,
        agent_id: str = "default",
    ) -> Optional[GraphNode]:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return None
            if type is not None:
                node.type = type
            if properties is not None:
                node.properties.update(properties)
            if text_content is not None:
                node.text_content = text_content
            node.updated_at = datetime.now()
            return node

    def delete_node(self, node_id: str, cascade: bool = False, agent_id: str = "default") -> bool:
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            if cascade:
                self._edges = {
                    eid: e
                    for eid, e in self._edges.items()
                    if e.source_id != node_id and e.target_id != node_id
                }
            return True

    def search_nodes(
        self,
        node_type: Optional[str] = None,
        properties_filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        agent_id: str = "default",
    ) -> SearchResult:
        with self._lock:
            items = list(self._nodes.values())
        if node_type is not None:
            items = [n for n in items if n.type == node_type]
        if properties_filter:
            items = [
                n for n in items
                if all(n.properties.get(k) == v for k, v in properties_filter.items())
            ]
        total = len(items)
        items = items[offset:offset + limit]
        return SearchResult(items=items, total=total, offset=offset, limit=limit)

    # ---------------- 边 ----------------
    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Optional[Dict[str, Any]] = None,
        text_content: Optional[str] = None,
        agent_id: str = "default",
    ) -> GraphEdge:
        edge = GraphEdge.create(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=dict(properties or {}),
            text_content=text_content,
            agent_id=agent_id,
        )
        with self._lock:
            self._edges[edge.id] = edge
        return edge

    def get_edge(self, edge_id: str, agent_id: str = "default") -> Optional[GraphEdge]:
        with self._lock:
            return self._edges.get(edge_id)

    def update_edge(
        self,
        edge_id: str,
        properties: Optional[Dict[str, Any]] = None,
        relation_type: Optional[str] = None,
        text_content: Optional[str] = None,
        agent_id: str = "default",
    ) -> Optional[GraphEdge]:
        with self._lock:
            edge = self._edges.get(edge_id)
            if edge is None:
                return None
            if relation_type is not None:
                edge.relation_type = relation_type
            if properties is not None:
                edge.properties.update(properties)
            if text_content is not None:
                edge.text_content = text_content
            return edge

    def delete_edge(self, edge_id: str, agent_id: str = "default") -> bool:
        with self._lock:
            return self._edges.pop(edge_id, None) is not None

    def search_edges(
        self,
        relation_type: Optional[str] = None,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        properties_filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        agent_id: str = "default",
    ) -> SearchResult:
        with self._lock:
            items = list(self._edges.values())
        if relation_type is not None:
            items = [e for e in items if e.relation_type == relation_type]
        if source_id is not None:
            items = [e for e in items if e.source_id == source_id]
        if target_id is not None:
            items = [e for e in items if e.target_id == target_id]
        if properties_filter:
            items = [
                e for e in items
                if all(e.properties.get(k) == v for k, v in properties_filter.items())
            ]
        total = len(items)
        items = items[offset:offset + limit]
        return SearchResult(items=items, total=total, offset=offset, limit=limit)

    # ---------------- 遍历 ----------------
    def _get_edges_for_node(
        self, node_id: str, direction: str = "both", agent_id: str = "default"
    ) -> List[GraphEdge]:
        with self._lock:
            edges = list(self._edges.values())
        if direction == "outgoing":
            return [e for e in edges if e.source_id == node_id]
        if direction == "incoming":
            return [e for e in edges if e.target_id == node_id]
        return [e for e in edges if e.source_id == node_id or e.target_id == node_id]

    def get_neighbor_ids(
        self, node_id: str, direction: str = "both", agent_id: str = "default"
    ) -> List[str]:
        ids: List[str] = []
        seen = set()
        for edge in self._get_edges_for_node(node_id, direction, agent_id):
            other = edge.target_id if edge.source_id == node_id else edge.source_id
            if other not in seen:
                seen.add(other)
                ids.append(other)
        return ids

    def get_neighbors(
        self,
        node_id: str,
        max_depth: int = 1,
        direction: str = "both",
        agent_id: str = "default",
    ) -> List[Tuple[GraphNode, List[GraphEdge]]]:
        """BFS 邻居查询，返回 (node, incident_edges) 列表（不含起始节点）。"""
        result: List[Tuple[GraphNode, List[GraphEdge]]] = []
        visited = set()
        queue = deque([(node_id, 0)])
        while queue:
            current_id, depth = queue.popleft()
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)
            if depth > 0:
                node = self.get_node(current_id, agent_id)
                if node is not None:
                    edges = self._get_edges_for_node(current_id, direction, agent_id)
                    result.append((node, edges))
            if depth < max_depth:
                for neighbor_id in self.get_neighbor_ids(current_id, direction, agent_id):
                    if neighbor_id not in visited:
                        queue.append((neighbor_id, depth + 1))
        return result

    def all_paths(
        self,
        start_id: str,
        end_id: str,
        max_length: int = 5,
        agent_id: str = "default",
    ) -> List[PathResult]:
        """DFS 枚举所有简单路径（沿出边方向）。"""
        results: List[PathResult] = []

        def dfs(current: str, path: List[str], edges: List[GraphEdge], depth: int) -> None:
            if current == end_id:
                results.append(
                    PathResult(path=list(path), edges=list(edges), length=len(path) - 1)
                )
                return
            if depth >= max_length:
                return
            for edge in self._get_edges_for_node(current, "outgoing", agent_id):
                neighbor = edge.target_id
                if neighbor not in path:
                    path.append(neighbor)
                    edges.append(edge)
                    dfs(neighbor, path, edges, depth + 1)
                    path.pop()
                    edges.pop()

        dfs(start_id, [start_id], [], 0)
        return results

    def shortest_path(
        self,
        start_id: str,
        end_id: str,
        max_length: int = 10,
        agent_id: str = "default",
    ) -> Optional[PathResult]:
        """BFS 最短路径（沿出边方向）。"""
        if start_id == end_id:
            return PathResult(path=[start_id], edges=[], length=0)
        visited = {start_id}
        queue = deque([(start_id, [start_id], [])])
        while queue:
            current, path, edges = queue.popleft()
            if len(path) - 1 >= max_length:
                continue
            for edge in self._get_edges_for_node(current, "outgoing", agent_id):
                neighbor = edge.target_id
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                new_edges = edges + [edge]
                if neighbor == end_id:
                    return PathResult(path=new_path, edges=new_edges, length=len(new_path) - 1)
                visited.add(neighbor)
                queue.append((neighbor, new_path, new_edges))
        return None


class InMemoryGraphStore(GraphStoreBase):
    """基于内存的图存储假实现（实现 ``GraphStoreBase`` 契约）。

    所有数据保存在底层 ``InMemoryGraphDatabase`` 的内存结构中，行为对齐
    ``SQLiteGraphStore``：Entity 映射为 GraphNode（type=``{library}_{entity_type}``），
    Relation 映射为 GraphEdge（relation_type=``{library}_{relation_type}``）。
    """

    def __init__(self, graph_database: InMemoryGraphDatabase):
        self._db = graph_database

    def _agent_id(self) -> str:
        return getattr(self._db, "agent_id", "default")

    def _node_type(self, library: GraphLibrary, entity_type: str) -> str:
        return f"{library.value}_{entity_type}"

    def _edge_type(self, library: GraphLibrary, relation_type: str) -> str:
        return f"{library.value}_{relation_type}"

    def _entity_from_node(self, node: GraphNode, library: GraphLibrary) -> Entity:
        props = node.properties or {}
        return Entity(
            entity_id=node.id,
            name=props.get("name", ""),
            entity_type=props.get("entity_type", ""),
            properties={
                k: v
                for k, v in props.items()
                if k not in ("name", "entity_type", "library", "memory_ids")
            },
            memory_ids=props.get("memory_ids", []),
            created_at=node.created_at if hasattr(node, "created_at") else datetime.now(),
            updated_at=node.updated_at if hasattr(node, "updated_at") else datetime.now(),
        )

    def _relation_from_edge(self, edge: GraphEdge) -> Relation:
        props = edge.properties or {}
        relation_type = props.get(
            "original_relation_type",
            edge.relation_type.split("_", 1)[-1] if "_" in edge.relation_type else edge.relation_type,
        )
        return Relation(
            from_entity=edge.source_id,
            to_entity=edge.target_id,
            relation_type=relation_type,
            strength=props.get("strength", 1.0),
            evidence_memory_ids=props.get("evidence_memory_ids", []),
            created_at=edge.created_at if hasattr(edge, "created_at") else datetime.now(),
        )

    # ---------------- GraphStoreBase 契约 ----------------
    def create_entity(self, entity: Entity, library: GraphLibrary) -> Entity:
        node_type = self._node_type(library, entity.entity_type)
        properties = {
            "name": entity.name,
            "entity_type": entity.entity_type,
            "library": library.value,
            "memory_ids": entity.memory_ids,
            **entity.properties,
        }
        node = self._db.add_node(
            node_type=node_type,
            properties=properties,
            text_content=entity.name,
            agent_id=self._agent_id(),
        )
        return self._entity_from_node(node, library)

    def create_relation(self, relation: Relation, library: GraphLibrary) -> Relation:
        edge_type = self._edge_type(library, relation.relation_type)
        properties = {
            "original_relation_type": relation.relation_type,
            "strength": relation.strength,
            "evidence_memory_ids": relation.evidence_memory_ids,
        }
        edge = self._db.add_edge(
            source_id=relation.from_entity,
            target_id=relation.to_entity,
            relation_type=edge_type,
            properties=properties,
            text_content=f"{relation.from_entity} {relation.relation_type} {relation.to_entity}",
            agent_id=self._agent_id(),
        )
        return self._relation_from_edge(edge)

    def get_entity(self, entity_id: str, library: GraphLibrary) -> Optional[Entity]:
        node = self._db.get_node(entity_id, agent_id=self._agent_id())
        if node is None:
            return None
        return self._entity_from_node(node, library)

    def find_related_entities(
        self,
        entity_id: str,
        relation_type: Optional[str],
        library: GraphLibrary,
        depth: int = 1,
    ) -> List[Entity]:
        neighbors = self._db.get_neighbors(
            entity_id, max_depth=depth, direction="both", agent_id=self._agent_id()
        )
        entities: List[Entity] = []
        for node, edges in neighbors:
            if relation_type is not None:
                wanted = self._edge_type(library, relation_type)
                if not any(e.relation_type == wanted for e in edges):
                    continue
            entities.append(self._entity_from_node(node, library))
        return entities

    def find_paths(
        self,
        start_entity_id: str,
        end_entity_id: str,
        library: GraphLibrary,
        max_depth: int = 3,
    ) -> List[List[Entity]]:
        paths = self._db.all_paths(
            start_entity_id, end_entity_id, max_length=max_depth, agent_id=self._agent_id()
        )
        result: List[List[Entity]] = []
        for path in paths:
            path_entities: List[Entity] = []
            for nid in path.path:
                entity = self.get_entity(nid, library)
                if entity is not None:
                    path_entities.append(entity)
            if path_entities:
                result.append(path_entities)
        return result

    def delete_entity(
        self, entity_id: str, library: GraphLibrary, hard: bool = False
    ) -> bool:
        if hard:
            self._db.delete_node(entity_id, cascade=True, agent_id=self._agent_id())
            return True
        node = self._db.get_node(entity_id, agent_id=self._agent_id())
        if node is not None:
            existing = dict(node.properties or {})
            existing["deleted"] = True
            self._db.update_node(entity_id, properties=existing, agent_id=self._agent_id())
        # 对齐 SQLiteGraphStore：无论实体是否存在均返回 True
        return True

    def delete_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        library: GraphLibrary,
        hard: bool = False,
    ) -> bool:
        edge_type = self._edge_type(library, relation_type)
        result = self._db.search_edges(
            relation_type=edge_type, source_id=from_entity, limit=100, agent_id=self._agent_id()
        )
        for edge in result.items:
            if edge.target_id == to_entity:
                if hard:
                    return self._db.delete_edge(edge.id, agent_id=self._agent_id())
                existing = dict(edge.properties or {})
                existing["deleted"] = True
                self._db.update_edge(edge.id, properties=existing, agent_id=self._agent_id())
                return True
        return False

    def update_entity(
        self, entity_id: str, updates: Dict, library: GraphLibrary
    ) -> Optional[Entity]:
        node = self._db.get_node(entity_id, agent_id=self._agent_id())
        if node is None:
            return None
        existing = dict(node.properties or {})
        existing.update(updates)
        node = self._db.update_node(
            entity_id, properties=existing, agent_id=self._agent_id()
        )
        if node is None:
            return None
        return self._entity_from_node(node, library)

    def update_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        updates: Dict,
        library: GraphLibrary,
    ) -> Optional[Relation]:
        edge_type = self._edge_type(library, relation_type)
        result = self._db.search_edges(
            relation_type=edge_type, source_id=from_entity, limit=100, agent_id=self._agent_id()
        )
        for edge in result.items:
            if edge.target_id == to_entity:
                existing = dict(edge.properties or {})
                existing.update(updates)
                updated = self._db.update_edge(
                    edge.id, properties=existing, agent_id=self._agent_id()
                )
                if updated is not None:
                    return self._relation_from_edge(updated)
        return None

    def get_stats(self, library: GraphLibrary) -> dict:
        node_prefix = f"{library.value}_"
        edge_prefix = f"{library.value}_"
        nodes = self._db.search_nodes(limit=10000, agent_id=self._agent_id())
        edges = self._db.search_edges(limit=10000, agent_id=self._agent_id())
        entity_count = sum(1 for n in nodes.items if n.type.startswith(node_prefix))
        relation_count = sum(1 for e in edges.items if e.relation_type.startswith(edge_prefix))
        return {
            "library": library.value,
            "entity_count": entity_count,
            "relation_count": relation_count,
        }

    def export(self, library: GraphLibrary) -> dict:
        node_prefix = f"{library.value}_"
        edge_prefix = f"{library.value}_"
        nodes = self._db.search_nodes(limit=10000, agent_id=self._agent_id())
        edges = self._db.search_edges(limit=10000, agent_id=self._agent_id())
        entities = [
            self._entity_from_node(n, library)
            for n in nodes.items
            if n.type.startswith(node_prefix)
        ]
        relations = [
            self._relation_from_edge(e)
            for e in edges.items
            if e.relation_type.startswith(edge_prefix)
        ]
        return {
            "library": library.value,
            "entities": [
                {
                    "id": e.entity_id,
                    "name": e.name,
                    "type": e.entity_type,
                    "properties": e.properties,
                }
                for e in entities
            ],
            "relations": [
                {
                    "from": r.from_entity,
                    "to": r.to_entity,
                    "type": r.relation_type,
                    "strength": r.strength,
                }
                for r in relations
            ],
        }


def make_in_memory_graph_store(
    agent_id: str = "default",
) -> Tuple[InMemoryGraphDatabase, InMemoryGraphStore]:
    """工厂函数：创建并返回 (InMemoryGraphDatabase, InMemoryGraphStore) 元组。"""
    gdb = InMemoryGraphDatabase(agent_id=agent_id)
    gdb.initialize()
    gs = InMemoryGraphStore(gdb)
    return gdb, gs
